import re

from bot.db import get_db
from bot.services.timeutil import now_utc

SETTING_FIELDS = {"sig": "signature", "bak": "backup_url", "pre": "premium_url"}


async def upsert(tg_chat_id: int, title: str, username: str | None) -> bool:
    """Store or refresh a channel. Returns True if it is new."""
    result = await get_db().channels.update_one(
        {"tg_chat_id": tg_chat_id},
        {
            "$set": {"title": title, "username": username},
            "$setOnInsert": {
                "tg_chat_id": tg_chat_id,
                "signature": "",
                "backup_url": None,
                "premium_url": None,
                "protect_content": False,
                "added_at": now_utc(),
            },
        },
        upsert=True,
    )
    return result.upserted_id is not None


async def get(tg_chat_id: int) -> dict | None:
    return await get_db().channels.find_one({"tg_chat_id": tg_chat_id})


async def find_by_username(username: str) -> dict | None:
    return await get_db().channels.find_one(
        {"username": {"$regex": f"^{re.escape(username)}$", "$options": "i"}}
    )


async def list_all() -> list[dict]:
    return await get_db().channels.find().sort("title", 1).to_list(None)


async def remove(tg_chat_id: int) -> bool:
    result = await get_db().channels.delete_one({"tg_chat_id": tg_chat_id})
    return result.deleted_count > 0


async def set_fields(tg_chat_id: int, **fields) -> None:
    await get_db().channels.update_one({"tg_chat_id": tg_chat_id}, {"$set": fields})
