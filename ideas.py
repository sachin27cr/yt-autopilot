"""Topic finder: pulls what US audiences are talking about and asks Claude for 5 ranked ideas."""
import requests

import market
from channels import Channel
from llm import ask_json

REDDIT_SUBS = {
    "A": ["CryptoCurrency", "Bitcoin", "solana", "ethereum", "stocks"],
    "B": ["business", "Economics", "investing", "todayilearned", "Entrepreneur"],
}


def reddit_top(subs: list[str], limit: int = 8) -> list[str]:
    """Top posts of the week. Reddit sometimes blocks cloud IPs; failures are skipped."""
    out = []
    for sub in subs:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/top.json",
                params={"t": "week", "limit": limit},
                headers={"User-Agent": "yt-autopilot-research/1.0"},
                timeout=15,
            )
            if not r.ok:
                continue
            for child in r.json()["data"]["children"]:
                d = child["data"]
                out.append(f"[r/{sub}] {d['title']} ({d.get('score', 0)} upvotes)")
        except Exception:  # noqa: BLE001
            continue
    return out


def get_ideas(ch: Channel, recent_titles: list[str]) -> list[dict]:
    """Return 5 ideas: [{"title", "pitch", "format"}]."""
    context = []
    if ch.key == "A":
        context.append(market.snapshot_text(market.snapshot(("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"))))
    posts = reddit_top(REDDIT_SUBS.get(ch.key, []))
    if posts:
        context.append("WHAT US REDDIT IS DISCUSSING THIS WEEK:\n" + "\n".join(posts[:40]))

    if ch.key == "A":
        format_rule = (
            "Idea 1 MUST be format 'recap' (the weekly market recap, framed around this week's single biggest story "
            "in the data). Ideas 2-5 are format 'flash': one event or data story explained in about 5 minutes."
        )
    else:
        format_rule = (
            "All ideas are format 'documentary': the story of one company, founder decision, collapse or comeback. "
            "Mix 2 ideas tied to current news with 3 evergreen stories with proven US search interest."
        )

    system = (
        f"You are the content strategist for the faceless YouTube channel '{ch.name}'. {ch.style}\n"
        "You pick topics a US audience is actively curious about right now, with a clear hook and a reason to click. "
        "Avoid clickbait that the video cannot deliver. Never pitch financial advice or price predictions."
    )
    user = (
        "\n\n".join(context)
        + f"\n\nRECENTLY PUBLISHED (do not repeat or closely overlap):\n" + "\n".join(f"- {t}" for t in recent_titles[-40:])
        + f"\n\n{format_rule}\n\n"
        'Reply with ONLY JSON: [{"title": "working title under 70 chars", '
        '"pitch": "one sentence: the hook and why now", "format": "recap|flash|documentary"}] with exactly 5 items, '
        "ranked best first."
    )
    ideas = ask_json(system, user, max_tokens=2000)
    cleaned = []
    for idea in ideas[:5]:
        fmt = idea.get("format", "")
        if fmt not in ch.formats:
            fmt = next(iter(ch.formats))
        cleaned.append({"title": str(idea.get("title", ""))[:90], "pitch": str(idea.get("pitch", ""))[:240], "format": fmt})
    return cleaned
