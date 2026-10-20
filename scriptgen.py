"""Script writer: turns a picked idea + your angle into a scene-by-scene video plan (JSON)."""
import random

import market
from channels import SUPPORTED_SYMBOLS, Channel
from config import WORDS_PER_MINUTE
from llm import ask_json

HOOK_STYLES = [
    "Open on the single most surprising number, then the question it raises.",
    "Open in the middle of the key moment, then rewind.",
    "Open with a common belief, then the data or fact that breaks it.",
    "Open with a direct question to the viewer about what they would have done.",
    "Open with a before/after contrast in two sentences.",
]
STRUCTURES = {
    "recap": [
        "Biggest move -> why it happened -> positioning data (funding, OI, long/short) -> what to watch next week.",
        "Three numbers that defined the week, one segment each -> how they connect -> what to watch next week.",
        "The week as a story in three acts (start, turn, close) -> the data under each act -> what to watch next week.",
    ],
    "flash": [
        "What happened -> the data behind it -> two scenarios to watch.",
        "The question everyone is asking -> what the data says -> what would change the picture.",
    ],
    "documentary": [
        "Cold open on the turning point -> origin -> rise -> the mistake or breakthrough -> where it stands now -> the lesson.",
        "The question (why did X happen?) -> three clues in order -> the answer -> what it means today.",
        "Two rivals side by side -> the fork in the road -> who won and why -> the lesson.",
    ],
}

VISUAL_SPEC = {
    "title": '{"type":"title","text":"max 8 words"}',
    "stat": '{"type":"stat","value":"+18.4%","label":"max 6 words"}',
    "price_chart": '{"type":"price_chart","symbol":"SOLUSDT","days":7}',
    "funding_chart": '{"type":"funding_chart","symbol":"SOLUSDT","days":7}',
    "oi_chart": '{"type":"oi_chart","symbol":"SOLUSDT","days":7}',
    "ls_chart": '{"type":"ls_chart","symbol":"SOLUSDT","days":7}',
    "bar": '{"type":"bar","title":"max 8 words","labels":["A","B"],"values":[1.2,3.4],"unit":"$B"}',
    "timeline": '{"type":"timeline","events":[{"year":"1997","text":"max 10 words"}]}  (3-6 events)',
    "stock": '{"type":"stock","query":"2-4 word stock footage search, concrete and visual"}',
}


def _system(ch: Channel) -> str:
    rules = "\n".join(f"- {r}" for r in ch.rules)
    visuals = "\n".join(f"- {VISUAL_SPEC[v]}" for v in ch.visual_types)
    symbols = ", ".join(SUPPORTED_SYMBOLS)
    return f"""You write scripts for the faceless YouTube channel "{ch.name}". Audience: United States.
Voice: {ch.style}

HARD RULES
{rules}
- The creator's ANGLE must be clearly present: it is the channel's own take and the reason this video is original.
- Write for the ear: short sentences, no lists read aloud, no emojis, no stage directions in narration.
- Numbers in narration are written as a person would say them ("eighteen percent" is fine as "18%").

SCENES
Each scene is 1-4 sentences of narration (15-70 words) plus ONE visual. Change the visual every scene.
Allowed visuals (exact JSON shapes):
{visuals}
Chart symbols allowed: {symbols}. Chart "days" between 1 and 30.
Add "chapter": "short name" to the first scene of each new section (at least 3 sections, first scene included).

SHORTS
Also write vertical Shorts cut from the same story. Each Short: 2-4 scenes, 45-120 words total,
first sentence is a hook that works with no context, last sentence points to the full video.

Reply with ONLY this JSON:
{{"title": "YouTube title, under 70 chars, curiosity + clarity, no ALL CAPS words",
  "description": "2-3 sentence description for YouTube, plain text",
  "tags": ["8-15 tags"],
  "thumbnail_text": "2-4 punchy words",
  "sources": ["public sources relied on, as 'Publisher - topic' (may be empty for data-only videos)"],
  "scenes": [{{"narration": "...", "visual": {{...}}, "chapter": "optional"}}],
  "shorts": [{{"title": "under 60 chars", "scenes": [{{"narration": "...", "visual": {{...}}}}]}}]}}"""


def write_script(ch: Channel, idea: dict, angle: str, notes: list[str] | None = None, last_hook: str | None = None) -> dict:
    if not angle or not angle.strip():
        raise ValueError("An angle is required for every video (keeps content original under YouTube's policy).")

    fmt = idea.get("format") or next(iter(ch.formats))
    minutes = ch.formats.get(fmt, 8)
    hooks = [h for h in HOOK_STYLES if h != last_hook] or HOOK_STYLES
    hook = random.choice(hooks)
    structure = random.choice(STRUCTURES.get(fmt, STRUCTURES["flash"]))

    parts = []
    if ch.key == "A":
        days = 7 if fmt == "recap" else 3
        parts.append(market.snapshot_text(market.snapshot(("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"), days), days))
    parts.append(f"VIDEO\nTopic: {idea['title']}\nPitch: {idea.get('pitch', '')}\nFormat: {fmt}")
    parts.append(f"CREATOR'S ANGLE (must shape the video): {angle.strip()}")
    parts.append(f"HOOK STYLE: {hook}\nSTRUCTURE: {structure}")
    parts.append(
        f"LENGTH: about {minutes} minutes = about {minutes * WORDS_PER_MINUTE} words of narration across "
        f"{max(8, minutes * 3)}-{max(12, minutes * 5)} scenes. Write {ch.shorts_per_video} Shorts."
    )
    if notes:
        parts.append("REVISION NOTES FROM THE CREATOR (apply all of them):\n" + "\n".join(f"- {n}" for n in notes))

    script = ask_json(_system(ch), "\n\n".join(parts), max_tokens=16000)
    script = validate(script, ch)
    script["format"] = fmt
    script["hook_style"] = hook
    return script


def _fix_visual(v: dict, ch: Channel, narration: str) -> dict:
    if not isinstance(v, dict) or v.get("type") not in ch.visual_types:
        return {"type": "stock", "query": " ".join(narration.split()[:3])} if "stock" in ch.visual_types else {"type": "title", "text": narration[:60]}
    if v["type"].endswith("_chart"):
        if v.get("symbol") not in SUPPORTED_SYMBOLS:
            v["symbol"] = "BTCUSDT"
        try:
            v["days"] = max(1, min(30, int(v.get("days", 7))))
        except (TypeError, ValueError):
            v["days"] = 7
    if v["type"] == "bar":
        labels, values = v.get("labels", []), v.get("values", [])
        try:
            values = [float(x) for x in values]
        except (TypeError, ValueError):
            values = []
        if not labels or len(labels) != len(values):
            return {"type": "title", "text": v.get("title", narration[:60])}
        v["values"] = values
    if v["type"] == "timeline" and not v.get("events"):
        return {"type": "title", "text": narration[:60]}
    return v


def validate(script: dict, ch: Channel) -> dict:
    scenes = [s for s in script.get("scenes", []) if isinstance(s, dict) and str(s.get("narration", "")).strip()]
    if len(scenes) < 3:
        raise ValueError("Script came back with fewer than 3 scenes.")
    for s in scenes:
        s["narration"] = str(s["narration"]).strip()
        s["visual"] = _fix_visual(s.get("visual"), ch, s["narration"])
    script["scenes"] = scenes

    shorts = []
    for short in script.get("shorts", [])[: ch.shorts_per_video]:
        sc = [s for s in short.get("scenes", []) if isinstance(s, dict) and str(s.get("narration", "")).strip()]
        for s in sc:
            s["narration"] = str(s["narration"]).strip()
            s["visual"] = _fix_visual(s.get("visual"), ch, s["narration"])
        if sc:
            shorts.append({"title": str(short.get("title", script.get("title", "")))[:90], "scenes": sc})
    script["shorts"] = shorts
    script["title"] = str(script.get("title", "Untitled"))[:100]
    script["tags"] = [str(t)[:40] for t in script.get("tags", [])][:15]
    script["sources"] = [str(s) for s in script.get("sources", [])][:12]
    return script
