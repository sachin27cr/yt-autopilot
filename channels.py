"""Channel profiles. Channel A = market data recaps, Channel B = business documentaries.

Everything that makes the two channels look and sound different lives here, so the
same pipeline code serves both without them ever looking like duplicates.
"""
from dataclasses import dataclass, field

from config import env

# Binance USDT-M symbols the chart engine is allowed to request.
SUPPORTED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]


@dataclass
class Channel:
    key: str                      # "A" or "B"
    name: str
    voice_id: str | None
    refresh_token: str | None
    accent: str                   # hex colour used on charts, cards, thumbnails
    background: str
    category_id: str              # YouTube category (27 = Education)
    formats: dict                 # format -> target minutes
    visual_types: list
    style: str                    # tone / voice guidance for the script writer
    rules: list                   # hard rules injected into every script prompt
    long_days_et: list            # weekdays (Mon=0) for long-video publish slots, audience TZ
    long_time_et: str             # "HH:MM" audience TZ
    shorts_time_et: str           # daily Shorts slot, audience TZ
    shorts_per_video: int
    idea_days_ptb: tuple          # python-telegram-bot run_daily days (0 = Sunday ... 6 = Saturday)
    idea_time_local: str          # "HH:MM" in LOCAL_TZ
    hashtags: list = field(default_factory=list)
    description_footer: str = ""


CHANNELS = {
    "A": Channel(
        key="A",
        name=env("CHANNEL_NAME_A", "Chart Ledger"),
        voice_id=env("VOICE_ID_A"),
        refresh_token=env("YT_REFRESH_TOKEN_A"),
        accent="#22d3a6",
        background="#0b0f17",
        category_id="27",
        formats={"recap": 10, "flash": 5},
        visual_types=["title", "stat", "price_chart", "funding_chart", "oi_chart", "ls_chart", "bar", "stock"],
        style=(
            "Calm, sharp, data-first market analyst voice for US crypto and stock traders aged 22-40. "
            "Plain English, short sentences, every claim tied to a number shown on screen."
        ),
        rules=[
            "Never give financial advice: no 'buy', 'sell', 'go long', 'go short', entries, exits or price targets.",
            "Never predict prices. Describe what the data shows and what to watch, as scenarios.",
            "Never present the narrator as a named analyst, expert or persona. The narrator is the channel.",
            "Only quote numbers that appear in the MARKET DATA block or are widely reported public facts.",
        ],
        long_days_et=[0, 3],          # Monday recap, Thursday flash
        long_time_et="17:30",
        shorts_time_et="12:00",
        shorts_per_video=3,
        idea_days_ptb=(0, 3),         # ideas arrive Sunday and Wednesday evening IST
        idea_time_local="20:00",
        hashtags=["#crypto", "#bitcoin", "#solana", "#markets"],
        description_footer=(
            "Data: Binance USDT-M futures public API.\n"
            "This video is for education and information only. It is not financial advice."
        ),
    ),
    "B": Channel(
        key="B",
        name=env("CHANNEL_NAME_B", "Market Mechanics"),
        voice_id=env("VOICE_ID_B"),
        refresh_token=env("YT_REFRESH_TOKEN_B"),
        accent="#f5b942",
        background="#14110d",
        category_id="27",
        formats={"documentary": 14},
        visual_types=["title", "stat", "timeline", "bar", "stock"],
        style=(
            "Warm, curious documentary narrator for a general US audience aged 25-55. "
            "Story first: tension, turning points, people and decisions. Concrete details over adjectives."
        ),
        rules=[
            "Only state facts that are well documented in public reporting; avoid exact figures you are unsure of.",
            "List the public sources you relied on in the 'sources' field.",
            "No investment advice and no claims about what a stock will do next.",
            "Never present the narrator as a named expert or persona.",
        ],
        long_days_et=[5],             # Saturday
        long_time_et="10:00",
        shorts_time_et="13:00",
        shorts_per_video=3,
        idea_days_ptb=(4,),           # ideas arrive Thursday evening IST
        idea_time_local="20:00",
        hashtags=["#business", "#documentary", "#companies"],
        description_footer="Sources are listed above. Narration is AI-assisted; script written and reviewed by the channel.",
    ),
}


def get(key: str) -> Channel:
    return CHANNELS[key.upper()]
