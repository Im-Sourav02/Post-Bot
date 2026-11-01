from bot.db import get_db
from bot.services.timeutil import now_utc


async def is_admin(user_id: int) -> bool:
    return await get_db().admins.find_one({"user_id": user_id}, {"_id": 1}) is not None


async def add(user_id: int, added_by: int) -> bool:
    """Returns True if the user was newly added, False if already an admin."""
    result = await get_db().admins.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "added_by": added_by, "added_at": now_utc()}},
        upsert=True,
    )
    return result.upserted_id is not None


async def remove(user_id: int) -> bool:
    result = await get_db().admins.delete_one({"user_id": user_id})
    return result.deleted_count > 0


async def list_all() -> list[dict]:
    return await get_db().admins.find().sort("added_at", 1).to_list(None)
