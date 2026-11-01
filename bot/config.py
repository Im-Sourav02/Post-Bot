import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name} (see .env.example)")
    return value


def _int(name: str, value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise SystemExit(f"Environment variable {name} must be an integer") from None


API_ID = _int("API_ID", _required("API_ID"))
API_HASH = _required("API_HASH")
BOT_TOKEN = _required("BOT_TOKEN")
OWNER_ID = _int("OWNER_ID", _required("OWNER_ID"))

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017").strip()
DB_NAME = os.getenv("DB_NAME", "postbot").strip() or "postbot"

TIMEZONE = os.getenv("TIMEZONE", "UTC").strip() or "UTC"
try:
    TZ = ZoneInfo(TIMEZONE)
except ZoneInfoNotFoundError:
    raise SystemExit(f"Unknown TIMEZONE {TIMEZONE!r}; use an IANA name like 'UTC' or 'Asia/Kolkata'") from None

SCHEDULER_INTERVAL = _int("SCHEDULER_INTERVAL", os.getenv("SCHEDULER_INTERVAL", "15"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

WELCOME_IMAGE = BASE_DIR / "assets" / "welcome.jpg"

CAPTION_LIMIT = 1024
CHANNELS_PER_PAGE = 10
POSTS_PER_PAGE = 8
