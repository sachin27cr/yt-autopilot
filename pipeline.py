"""Job lifecycle: create -> produce (script, voice, visuals, render, thumbnail) -> publish or revise."""
import json
import shutil
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import channels
import render
import scriptgen
import store
import youtube
from config import AUDIENCE_TZ, DRY_RUN_UPLOAD, WORK_DIR
from thumbnail import make_thumbnail
from utils import log

JOBS_DIR = WORK_DIR / "jobs"


def create_job(ch_key: str, idea: dict, angle: str) -> str:
    job_id = store.new_id()
    store.save_job({
        "id": job_id, "channel": ch_key, "idea": idea, "angle": angle.strip(), "notes": [],
        "rev": 0, "status": "queued", "created": datetime.now(timezone.utc).isoformat(),
    })
    return job_id


def add_note(job_id: str, note: str) -> None:
    job = store.get_job(job_id)
    job["notes"].append(note.strip())
    job["status"] = "queued"
    store.save_job(job)


def reject(job_id: str) -> None:
    job = store.get_job(job_id)
    job["status"] = "rejected"
    store.save_job(job)
    _cleanup(job, keep_script=True)


def produce(job_id: str) -> dict:
    job = store.get_job(job_id)
    ch = channels.get(job["channel"])
    job["rev"] += 1
    job["status"] = "producing"
    store.save_job(job)
    job_dir = JOBS_DIR / job_id / f"rev{job['rev']}"
    job_dir.mkdir(parents=True, exist_ok=True)

    last_hook = store.read()["last_hook"].get(ch.key)
    script = scriptgen.write_script(ch, job["idea"], job["angle"], job["notes"], last_hook)
    (job_dir / "script.json").write_text(json.dumps(script, indent=2))
    store.update(lambda s: s["last_hook"].__setitem__(ch.key, script["hook_style"]))

    used_stock: set = set()
    long = render.produce_video(script["scenes"], ch, job_dir, "long", portrait=False, used_stock=used_stock)
    shorts = []
    for i, short in enumerate(script["shorts"]):
        try:
            out = render.produce_video(short["scenes"], ch, job_dir, f"short{i + 1}", portrait=True, used_stock=used_stock)
            out["title"] = short["title"]
            out["preview"] = render.make_preview(out["path"], portrait=True)
            shorts.append(out)
        except Exception as e:  # noqa: BLE001
            log.warning("Short %d failed: %s", i + 1, e)

    thumb = make_thumbnail(script.get("thumbnail_text") or script["title"], ch, job_dir / "thumbnail.jpg",
                           long["first_image"])
    long["preview"] = render.make_preview(long["path"])

    job.update(
        status="review", script=script, long=long, shorts=shorts, thumbnail=str(thumb),
        description=_long_description(ch, script, long),
    )
    store.save_job(job)
    return job


def _long_description(ch, script: dict, long: dict) -> str:
    parts = [script.get("description", "").strip()]
    chapters = render.chapter_block(long["chapters"], long["duration"])
    if chapters:
        parts.append(chapters)
    if script.get("sources"):
        parts.append("Sources:\n" + "\n".join(f"- {s}" for s in script["sources"]))
    parts.append(ch.description_footer)
    parts.append(" ".join(ch.hashtags))
    return "\n\n".join(p for p in parts if p)


def _slots(days: list | None, hhmm: str, count: int, taken: set, after: datetime) -> list[datetime]:
    tz = ZoneInfo(AUDIENCE_TZ)
    h, m = map(int, hhmm.split(":"))
    earliest = after + timedelta(hours=2)
    start: date = earliest.astimezone(tz).date()
    out = []
    for i in range(90):
        day = start + timedelta(days=i)
        if days is not None and day.weekday() not in days:
            continue
        slot = datetime.combine(day, time(h, m), tz)
        if slot <= earliest or slot.isoformat() in taken:
            continue
        out.append(slot)
        if len(out) == count:
            break
    return out


def publish(job_id: str) -> list[dict]:
    job = store.get_job(job_id)
    ch = channels.get(job["channel"])
    if job.get("status") != "review":
        raise RuntimeError(f"Job {job_id} is '{job.get('status')}', not ready to publish.")
    taken = set(store.read()["taken_slots"])
    now = datetime.now(timezone.utc)
    long_slot = _slots(ch.long_days_et, ch.long_time_et, 1, taken, now)[0]
    short_slots = _slots(None, ch.shorts_time_et, len(job["shorts"]), taken, long_slot)
    results = []

    def _up(path, title, desc, tags, when, thumb=None) -> str:
        if DRY_RUN_UPLOAD:
            log.info("DRY RUN: would upload %s at %s", title, when)
            return "DRYRUN"
        return youtube.upload(ch, path, title, desc, tags, when, thumb)

    script = job["script"]
    long_id = _up(job["long"]["path"], script["title"], job["description"], script["tags"], long_slot, job["thumbnail"])
    results.append({"title": script["title"], "id": long_id, "when": long_slot.isoformat()})

    for short, slot in zip(job["shorts"], short_slots):
        footer = f"{ch.description_footer}\n\n" if ch.key == "A" else ""
        desc = (f"{short['title']}\n\nFull video: https://youtu.be/{long_id}\n\n"
                f"{footer}{' '.join(ch.hashtags)} #Shorts")
        sid = _up(short["path"], short["title"], desc, script["tags"] + ["shorts"], slot)
        results.append({"title": short["title"], "id": sid, "when": slot.isoformat()})

    def _book(s):
        s["taken_slots"].extend(r["when"] for r in results)
        s["taken_slots"] = s["taken_slots"][-200:]
        s["history"].setdefault(ch.key, []).append(script["title"])

    store.update(_book)
    job["status"] = "published"
    job["uploads"] = results
    store.save_job(job)
    _cleanup(job, keep_script=True)
    return results


def _cleanup(job: dict, keep_script: bool) -> None:
    """Delete heavy render files after publish/reject; keep script.json for reference."""
    root = JOBS_DIR / job["id"]
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_dir() and path.name.endswith(("_parts", "assets")):
            shutil.rmtree(path, ignore_errors=True)
    for path in root.rglob("*.mp4"):
        path.unlink(missing_ok=True)
    if not keep_script:
        shutil.rmtree(root, ignore_errors=True)


def local_time(iso: str, tz_name: str) -> str:
    return datetime.fromisoformat(iso).astimezone(ZoneInfo(tz_name)).strftime("%a %d %b, %I:%M %p")
