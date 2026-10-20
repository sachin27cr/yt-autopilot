"""Offline self-test: renders a sample long video, a Short and a thumbnail with fake audio and
synthetic market data. Needs no API keys. Run:  python selftest.py
Output lands in WORK_DIR/selftest/.
"""
import numpy as np
import pandas as pd

import channels
import market
import render
from config import WORK_DIR
from thumbnail import make_thumbnail
from utils import run


def fake_market():
    t = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=42, freq="4h")
    rng = np.random.default_rng(7)
    close = 150 * np.cumprod(1 + rng.normal(0.002, 0.012, len(t)))
    market.klines = lambda s, d=7: pd.DataFrame({"t": t, "o": close * 0.995, "h": close * 1.01, "l": close * 0.99,
                                                   "c": close, "v": 1.0})
    ft = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=21, freq="8h")
    market.funding = lambda s, d=7: pd.DataFrame({"t": ft, "rate_pct": rng.normal(0.006, 0.01, len(ft))})
    market.open_interest = lambda s, d=7: pd.DataFrame({"t": t, "oi_usd": 2.1e9 * np.cumprod(1 + rng.normal(0.002, 0.01, len(t)))})
    market.long_short = lambda s, d=7: pd.DataFrame({"t": t, "ratio": 1.4 + rng.normal(0, 0.1, len(t))})


def fake_tts(text, voice_id, out_path):
    secs = max(1.5, len(text.split()) / 2.6)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={secs:.2f}", "-af", "volume=0.05",
         "-ar", "44100", "-ac", "2", "-b:a", "128k", out_path])
    return out_path


SCENES = [
    {"narration": "Solana just had its strongest week in two months, and the futures data tells a more cautious story.",
     "visual": {"type": "stat", "value": "+12.4%", "label": "SOL weekly change"}, "chapter": "The move"},
    {"narration": "Price climbed steadily from Monday, with the biggest push on Thursday after the ETF headlines.",
     "visual": {"type": "price_chart", "symbol": "SOLUSDT", "days": 7}},
    {"narration": "But funding stayed mostly positive, which means longs were paying shorts to keep their bets open.",
     "visual": {"type": "funding_chart", "symbol": "SOLUSDT", "days": 7}, "chapter": "Positioning"},
    {"narration": "Open interest grew alongside price, so new money came in rather than shorts simply closing.",
     "visual": {"type": "oi_chart", "symbol": "SOLUSDT", "days": 7}},
    {"narration": "And retail accounts lean long, with about one and a half longs for every short.",
     "visual": {"type": "ls_chart", "symbol": "SOLUSDT", "days": 7}},
    {"narration": "Here is how the three biggest coins compared this week.",
     "visual": {"type": "bar", "title": "Weekly change", "labels": ["BTC", "ETH", "SOL"], "values": [3.1, 5.4, 12.4], "unit": "%"},
     "chapter": "What to watch"},
    {"narration": "What to watch next week: whether funding cools while price holds.",
     "visual": {"type": "title", "text": "Funding cools while price holds?"}},
]

TIMELINE = [{"narration": "The company went from a garage to a giant in three decades.",
             "visual": {"type": "timeline", "events": [{"year": "1993", "text": "Founded in a Denny's booth"},
                                                       {"year": "2006", "text": "CUDA opens GPUs to science"},
                                                       {"year": "2023", "text": "AI demand explodes"}]}},
            {"narration": "And that is the real lesson of the story.", "visual": {"type": "title", "text": "The lesson"}}]


if __name__ == "__main__":
    fake_market()
    out = WORK_DIR / "selftest"
    out.mkdir(parents=True, exist_ok=True)
    a, b = channels.get("A"), channels.get("B")

    long = render.produce_video(SCENES, a, out, "long", synth=fake_tts)
    print("Long:", long["path"], f"{long['duration']:.1f}s")
    print("Chapters:\n" + render.chapter_block(long["chapters"], long["duration"]))
    short = render.produce_video(SCENES[:3], a, out, "short1", portrait=True, synth=fake_tts)
    print("Short:", short["path"], f"{short['duration']:.1f}s")
    doc = render.produce_video(TIMELINE, b, out, "docB", synth=fake_tts)
    print("Channel B sample:", doc["path"])
    print("Preview:", render.make_preview(long["path"]))
    print("Thumbnail:", make_thumbnail("SOL longs are paying", a, out / "thumb.jpg", long["first_image"]))
