import asyncio
import logging
from datetime import timezone

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from bot import config

log = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db


async def connect(attempts: int = 30, delay: float = 2.0) -> None:
    """Connect to MongoDB, retrying while the server comes up (e.g. in docker compose)."""
    global _client, _db
    _client = AsyncIOMotorClient(
        config.MONGO_URI,
        tz_aware=True,
        tzinfo=timezone.utc,
        serverSelectionTimeoutMS=5000,
    )
    _db = _client[config.DB_NAME]
    for attempt in range(1, attempts + 1):
        try:
            await _db.command("ping")
            log.info("Connected to MongoDB (database %r)", config.DB_NAME)
            break
        except Exception as e:
            if attempt == attempts:
                raise SystemExit(f"Could not connect to MongoDB: {type(e).__name__}") from None
            log.warning("MongoDB not reachable yet (attempt %d/%d), retrying...", attempt, attempts)
            await asyncio.sleep(delay)
    await ensure_indexes()


async def ensure_indexes() -> None:
    db = get_db()
    await db.posts.create_index([("status", ASCENDING), ("send_at", ASCENDING)])
    await db.posts.create_index([("status", ASCENDING), ("delete_at", ASCENDING)])
    await db.posts.create_index("token", unique=True)
    await db.posts.create_index([("channel_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)])
    await db.admins.create_index("user_id", unique=True)
    await db.channels.create_index("tg_chat_id", unique=True)
    await db.states.create_index("user_id", unique=True)


def close() -> None:
    if _client is not None:
        _client.close()
