"""Background loop that fires due scheduled sends and deletions. MongoDB is the source of truth."""
import asyncio
import logging

from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError

from bot import config
from bot.db import channels, posts
from bot.keyboards.posts import actions
from bot.services.errors import friendly
from bot.services.formatting import esc
from bot.services.poster import PostError, delete_live, publish
from bot.services.screens import post_sent
from bot.services.timeutil import fmt, now_utc
from bot.services.ui import NO_PREVIEW

log = logging.getLogger(__name__)

PURGE_EVERY = 240  # ticks (~1 hour at 15s)


async def run(client: Client) -> None:
    await posts.recover_interrupted()
    log.info("Scheduler started (every %ss)", config.SCHEDULER_INTERVAL)
    ticks = 0
    while True:
        try:
            await tick(client)
            if ticks % PURGE_EVERY == 0:
                await posts.purge_old_drafts()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Scheduler tick failed")
        ticks += 1
        await asyncio.sleep(config.SCHEDULER_INTERVAL)


async def tick(client: Client) -> None:
    now = now_utc()
    while post := await posts.claim_due_send(now):
        if not await _send(client, post):
            break
    while post := await posts.claim_due_delete(now):
        if not await _delete(client, post):
            break


async def _notify(client: Client, user_id: int, text: str, reply_markup=None) -> None:
    try:
        await client.send_message(user_id, text, reply_markup=reply_markup, link_preview_options=NO_PREVIEW)
    except Exception as e:
        log.info("Could not notify user %s: %s", user_id, getattr(e, "ID", type(e).__name__))


async def _send(client: Client, post: dict) -> bool:
    """Returns False when the loop should pause (rate limit)."""
    token = post["token"]
    try:
        sent = await publish(client, post)
    except FloodWait as e:
        log.warning("FloodWait %ss while sending scheduled post %s", e.value, token)
        await posts.update(token, status=posts.SCHEDULED)
        return False
    except (PostError, RPCError, OSError) as e:
        reason = e.text if isinstance(e, PostError) else friendly(e)
        log.warning("Scheduled post %s failed: %s", token, getattr(e, "ID", type(e).__name__))
        await posts.update(token, status=posts.CANCELLED, last_error=reason)
        await _notify(client, post["created_by"],
                      f"❌ <b>A scheduled post could not be sent</b> ({fmt(post.get('send_at'))}).\n\n{reason}")
        return True
    log.info("Scheduled post %s sent", token)
    channel = await channels.get(sent["channel_id"])
    await _notify(client, sent["created_by"], post_sent(sent, channel, client.me.username),
                  actions(sent, client.me.username))
    return True


async def _delete(client: Client, post: dict) -> bool:
    token = post["token"]
    try:
        await delete_live(client, post)
    except FloodWait as e:
        log.warning("FloodWait %ss while deleting post %s", e.value, token)
        await posts.update(token, status=posts.SENT)
        return False
    except (RPCError, OSError) as e:
        reason = friendly(e)
        log.warning("Scheduled deletion of %s failed: %s", token, getattr(e, "ID", type(e).__name__))
        await posts.update(token, status=posts.SENT, delete_at=None, last_error=reason)
        channel = await channels.get(post["channel_id"])
        title = esc(channel["title"]) if channel else "a removed channel"
        await _notify(client, post["created_by"],
                      f"⚠️ <b>Scheduled deletion failed</b> for a post in 📢 {title}.\n\n{reason}")
        return True
    await posts.update(token, status=posts.DELETED, deleted_at=now_utc())
    log.info("Post %s deleted on schedule", token)
    return True
