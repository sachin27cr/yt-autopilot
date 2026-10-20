"""Turns a list of scenes into a finished MP4: voice + visuals per scene, captions, loudness."""
import math
from pathlib import Path

import tts
import visuals
from channels import Channel
from config import FPS, LANDSCAPE, PORTRAIT
from utils import log, probe_duration, run, srt_ts

SCENE_PAD = 0.35  # seconds of breathing room after each scene's narration

ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
          "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]


def render_scene(kind: str, asset: Path, audio: Path, dur: float, W: int, H: int, out: Path) -> Path:
    if kind == "image":
        frames = math.ceil(dur * FPS) + 5
        vf = (f"[0:v]scale={W * 2}:{H * 2},"
              f"zoompan=z='min(zoom+0.0004,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={W}x{H}:fps={FPS},setsar=1,format=yuv420p[v];[1:a]apad[a]")
        cmd = ["ffmpeg", "-y", "-i", asset, "-i", audio]
    else:
        vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,"
              f"eq=brightness=-0.04:saturation=0.95,format=yuv420p[v];[1:a]apad[a]")
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", asset, "-i", audio]
    cmd += ["-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}", *ENCODE, out]
    run(cmd)
    return out


def build_srt(scenes: list[dict], durations: list[float], words_per_cue: int) -> str:
    cues, t, n = [], 0.0, 1
    for scene, dur in zip(scenes, durations):
        words = scene["narration"].split()
        speak = max(dur - SCENE_PAD, 0.5)
        chunks = [" ".join(words[i:i + words_per_cue]) for i in range(0, len(words), words_per_cue)]
        total_chars = sum(len(c) for c in chunks) or 1
        cursor = t
        for chunk in chunks:
            span = speak * len(chunk) / total_chars
            cues.append(f"{n}\n{srt_ts(cursor)} --> {srt_ts(cursor + span - 0.02)}\n{chunk}\n")
            cursor += span
            n += 1
        t += dur
    return "\n".join(cues)


def produce_video(scenes: list[dict], ch: Channel, job_dir: Path, name: str, portrait: bool = False,
                  used_stock: set | None = None, synth=None) -> dict:
    """Render scenes into job_dir/<name>.mp4. `synth` lets the self-test swap in fake audio."""
    synth = synth or tts.synth
    used_stock = used_stock if used_stock is not None else set()
    W, H = PORTRAIT if portrait else LANDSCAPE
    parts_dir = job_dir / f"{name}_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    clips, durations, chapters, first_image = [], [], [], None
    t = 0.0
    for i, scene in enumerate(scenes):
        audio = synth(scene["narration"], ch.voice_id, parts_dir / f"s{i:02d}.mp3")
        dur = probe_duration(audio) + SCENE_PAD
        fallback = scene.get("chapter") or " ".join(scene["narration"].split()[:8])
        kind, asset = visuals.make_visual(scene["visual"], ch, W, H, job_dir / "assets", f"{name}_s{i:02d}",
                                          used_stock, fallback)
        if kind == "image" and first_image is None and scene["visual"]["type"] != "title":
            first_image = asset
        clip = render_scene(kind, asset, audio, dur, W, H, parts_dir / f"s{i:02d}.mp4")
        clips.append(clip)
        durations.append(dur)
        if scene.get("chapter"):
            chapters.append((t, str(scene["chapter"])))
        t += dur
        log.info("%s scene %d/%d done (%.1fs)", name, i + 1, len(scenes), dur)

    listing = parts_dir / "list.txt"
    listing.write_text("".join(f"file '{c.name}'\n" for c in clips))
    joined = parts_dir / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing.name, "-c", "copy", joined.name], cwd=parts_dir)

    srt = parts_dir / "captions.srt"
    srt.write_text(build_srt(scenes, durations, 4 if portrait else 7), encoding="utf-8")
    style = ("FontName=DejaVu Sans,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
             "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,"
             + ("FontSize=11,MarginV=70" if portrait else "FontSize=13,MarginV=24"))
    final = job_dir / f"{name}.mp4"
    run(["ffmpeg", "-y", "-i", joined.name, "-vf", f"subtitles=captions.srt:force_style='{style}'",
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart",
         str(final.resolve())], cwd=parts_dir)

    return {"path": str(final), "duration": sum(durations), "chapters": chapters,
            "first_image": str(first_image) if first_image else None}


def make_preview(src: str, portrait: bool = False) -> str:
    """Small copy for Telegram (bots can send up to 50 MB)."""
    out = str(Path(src).with_name(Path(src).stem + "_preview.mp4"))
    scale = "scale=-2:640" if portrait else "scale=-2:480"
    run(["ffmpeg", "-y", "-i", src, "-vf", scale, "-c:v", "libx264", "-preset", "veryfast", "-crf", "31",
         "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", out])
    return out


def chapter_block(chapters: list[tuple[float, str]], total: float) -> str:
    """YouTube chapters need 0:00 first, at least 3 entries, each at least 10 s long."""
    from utils import fmt_ts
    if not chapters:
        return ""
    if chapters[0][0] > 0.5:
        chapters = [(0.0, "Intro")] + chapters
    else:
        chapters = [(0.0, chapters[0][1])] + chapters[1:]
    kept = [chapters[0]]
    for start, label in chapters[1:]:
        if start - kept[-1][0] >= 10 and total - start >= 10:
            kept.append((start, label))
    if len(kept) < 3:
        return ""
    return "\n".join(f"{fmt_ts(s)} {label}" for s, label in kept)
