import secrets
from datetime import datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from bot.db import get_db
from bot.services.timeutil import now_utc

# Public lifecycle: draft -> scheduled -> sent -> deleted, or cancelled.
# "sending" and "deleting" are short-lived claims that stop two workers acting on the same post.
DRAFT, SCHEDULED, SENDING, SENT, DELETING, DELETED, CANCELLED = (
    "draft", "scheduled", "sending", "sent", "deleting", "deleted", "cancelled",
)
ACTIVE = [SCHEDULED, SENDING, SENT, DELETING]

LIST_FILTERS = {
    "a": ({"status": {"$in": ACTIVE}}, [("created_at", -1)]),
    "s": ({"status": SCHEDULED}, [("send_at", 1)]),
    "t": ({"status": SENT}, [("sent_at", -1)]),
}


def _col():
    return get_db().posts


async def create(channel_id: int, created_by: int, **fields) -> dict:
    doc = {
        "channel_id": channel_id,
        "media_type": None,
        "file_id": None,
        "caption_html": "",
        "download_url": None,
        "status": DRAFT,
        "message_id": None,
        "send_at": None,
        "sent_at": None,
        "delete_at": None,
        "delete_delay": None,
        "created_by": created_by,
        "created_at": now_utc(),
        **fields,
    }
    for _ in range(5):
        doc["token"] = secrets.token_urlsafe(6)
        try:
            await _col().insert_one(doc)
            return doc
        except DuplicateKeyError:
            doc.pop("_id", None)
    raise RuntimeError("Could not generate a unique post token")


async def get(token: str) -> dict | None:
    return await _col().find_one({"token": token})


async def update(token: str, **fields) -> dict | None:
    return await _col().find_one_and_update(
        {"token": token}, {"$set": fields}, return_document=ReturnDocument.AFTER
    )


async def unset(token: str, *names: str) -> None:
    await _col().update_one({"token": token}, {"$unset": {n: "" for n in names}})


async def claim(token: str, from_status: str | list[str], to_status: str, **fields) -> dict | None:
    """Atomically move a post between statuses. Returns the updated post or None if it wasn't in from_status."""
    statuses = [from_status] if isinstance(from_status, str) else from_status
    return await _col().find_one_and_update(
        {"token": token, "status": {"$in": statuses}},
        {"$set": {"status": to_status, **fields}},
        return_document=ReturnDocument.AFTER,
    )


async def delete_draft(token: str) -> None:
    await _col().delete_one({"token": token, "status": DRAFT})


async def list_for_channel(channel_id: int, flt: str, page: int, per_page: int) -> tuple[list[dict], bool]:
    query, sort = LIST_FILTERS.get(flt, LIST_FILTERS["a"])
    cursor = _col().find({"channel_id": channel_id, **query}).sort(sort).skip(page * per_page).limit(per_page + 1)
    docs = await cursor.to_list(None)
    return docs[:per_page], len(docs) > per_page


async def claim_due_send(now: datetime) -> dict | None:
    return await _col().find_one_and_update(
        {"status": SCHEDULED, "send_at": {"$lte": now}},
        {"$set": {"status": SENDING}},
        sort=[("send_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


async def claim_due_delete(now: datetime) -> dict | None:
    return await _col().find_one_and_update(
        {"status": SENT, "delete_at": {"$ne": None, "$lte": now}},
        {"$set": {"status": DELETING}},
        sort=[("delete_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


async def cancel_scheduled_for_channel(channel_id: int) -> int:
    result = await _col().update_many(
        {"channel_id": channel_id, "status": SCHEDULED}, {"$set": {"status": CANCELLED}}
    )
    return result.modified_count


async def recover_interrupted() -> None:
    """Release claims left behind by a crash so the scheduler can pick the posts up again."""
    col = _col()
    await col.update_many({"status": SENDING, "message_id": {"$ne": None}}, {"$set": {"status": SENT}})
    await col.update_many({"status": SENDING, "send_at": {"$ne": None}}, {"$set": {"status": SCHEDULED}})
    await col.update_many({"status": SENDING}, {"$set": {"status": DRAFT}})
    await col.update_many({"status": DELETING}, {"$set": {"status": SENT}})


async def purge_old_drafts(max_age: timedelta = timedelta(days=3)) -> None:
    await _col().delete_many({"status": DRAFT, "created_at": {"$lt": now_utc() - max_age}})
