"""Central configuration. Every secret comes from environment variables (Railway → Variables)."""
import os
from pathlib import Path


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


# --- AI services -------------------------------------------------------------
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
CLAUDE_MODEL = env("CLAUDE_MODEL", "claude-sonnet-5-5")

ELEVENLABS_API_KEY = env("ELEVENLABS_API_KEY")
ELEVENLABS_MODEL = env("ELEVENLABS_MODEL", "eleven_multilingual_v2")

PEXELS_API_KEY = env("PEXELS_API_KEY")

# --- Telegram ----------------------------------------------------------------
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(env("TELEGRAM_CHAT_ID", "0") or 0)

# --- YouTube (one Google Cloud OAuth client, one refresh token per channel) ---
YT_CLIENT_ID = env("YT_CLIENT_ID")
YT_CLIENT_SECRET = env("YT_CLIENT_SECRET")
DRY_RUN_UPLOAD = env("DRY_RUN_UPLOAD", "0") == "1"  # 1 = render + preview, never upload

# --- Market data ---------------------------------------------------------------
# Binance blocks US IPs. Deploy the Railway service in an EU or Asia region.
BINANCE_FAPI = env("BINANCE_FAPI", "https://fapi.binance.com")

# --- Storage -------------------------------------------------------------------
# On Railway, mount a volume at /data and set WORK_DIR=/data
WORK_DIR = Path(env("WORK_DIR", "./work"))
WORK_DIR.mkdir(parents=True, exist_ok=True)

# --- Fonts (installed by the Dockerfile via fonts-dejavu-core) -----------------
FONT_BOLD = env("FONT_BOLD", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
FONT_REGULAR = env("FONT_REGULAR", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

# --- Time zones ----------------------------------------------------------------
LOCAL_TZ = env("LOCAL_TZ", "Asia/Kolkata")       # where you approve from
AUDIENCE_TZ = env("AUDIENCE_TZ", "America/New_York")  # publish slots are in this zone

# --- Which channels the scheduler pushes ideas for (launch A first, add B later) ---
ENABLED_CHANNELS = [c.strip().upper() for c in (env("ENABLED_CHANNELS", "A") or "A").split(",") if c.strip()]

# --- Video ---------------------------------------------------------------------
FPS = 30
LANDSCAPE = (1920, 1080)
PORTRAIT = (1080, 1920)
WORDS_PER_MINUTE = 150
