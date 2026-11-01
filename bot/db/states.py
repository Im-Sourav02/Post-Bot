"""Per-user conversation state, persisted so flows survive restarts."""
from bot.db import get_db
from bot.services.timeutil import now_utc


async def get(user_id: int) -> dict | None:
    return await get_db().states.find_one({"user_id": user_id})


async def set(user_id: int, step: str, data: dict | None = None) -> None:
    await get_db().states.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "step": step, "data": data or {}, "updated_at": now_utc()}},
        upsert=True,
    )


async def clear(user_id: int) -> None:
    await get_db().states.delete_one({"user_id": user_id})
