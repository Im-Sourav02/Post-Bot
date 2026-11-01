import re
from datetime import datetime, timezone

from bot import config

INPUT_FORMAT = "%d/%m/%Y %H:%M"
INPUT_HINT = "DD/MM/YYYY HH:MM"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_local(text: str) -> datetime | None:
    """Parse 'DD/MM/YYYY HH:MM' in the configured timezone and return an aware UTC datetime."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    try:
        local = datetime.strptime(cleaned, INPUT_FORMAT)
    except ValueError:
        return None
    return local.replace(tzinfo=config.TZ).astimezone(timezone.utc)


def fmt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(config.TZ).strftime(INPUT_FORMAT)


def now_local_str() -> str:
    return fmt(now_utc())
