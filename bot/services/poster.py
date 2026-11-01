"""Publishing posts to channels and keeping the live channel post in sync with edits."""
import logging
from datetime import timedelta

from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError

from bot.db import channels, posts
from bot.keyboards.posts import post_markup
from bot.services import media
from bot.services.errors import friendly, is_message_gone, is_not_modified
from bot.services.formatting import caption_overflow, compose_caption, too_long_text
from bot.services.timeutil import now_utc

log = logging.getLogger(__name__)


class PostError(Exception):
    """A problem that should be shown to the admin as-is."""

    def __init__(self, text: str):
        super().__init__(text)
        self.text = text


def full_caption(post: dict, channel: dict) -> str:
    return compose_caption(post.get("caption_html"), channel.get("signature"))


async def channel_for(post: dict) -> dict:
    channel = await channels.get(post["channel_id"])
    if not channel:
        raise PostError("📢 This post's channel was removed from the bot.")
    return channel


async def publish(client: Client, post: dict) -> dict:
    """Send a claimed post (status 'sending') to its channel and mark it sent."""
    channel = await channel_for(post)
    if caption_overflow(post.get("caption_html"), channel.get("signature")):
        raise PostError(too_long_text(post.get("caption_html"), channel.get("signature")))
    msg = await media.send(
        client,
        channel["tg_chat_id"],
        post["media_type"],
        post["file_id"],
        full_caption(post, channel),
        post_markup(channel, post.get("download_url")),
        protect_content=bool(channel.get("protect_content")),
    )
    sent_at = now_utc()
    fields = {"status": posts.SENT, "message_id": msg.id, "sent_at": sent_at, "last_error": None}
    if post.get("delete_delay") and not post.get("delete_at"):
        fields["delete_at"] = sent_at + timedelta(seconds=post["delete_delay"])
    return await posts.update(post["token"], **fields)


async def send_now(client: Client, token: str, from_status: str = posts.DRAFT) -> tuple[dict | None, str | None]:
    """Claim and publish a post right away. Returns (post, None) or (None, error text)."""
    post = await posts.claim(token, from_status, posts.SENDING)
    if not post:
        return None, "ℹ️ This post was already sent or is no longer available."
    try:
        return await publish(client, post), None
    except PostError as e:
        await posts.update(token, status=from_status)
        return None, e.text
    except (RPCError, OSError) as e:
        log.warning("Sending post %s failed: %s", token, getattr(e, "ID", type(e).__name__))
        await posts.update(token, status=from_status)
        return None, friendly(e)


async def _live(post: dict, action) -> str | None:
    """Run a live edit. Returns None on success or a friendly error text."""
    try:
        await action()
        return None
    except FloodWait as e:
        return friendly(e)
    except RPCError as e:
        if is_not_modified(e):
            return None
        if is_message_gone(e):
            await posts.update(post["token"], status=posts.DELETED, delete_at=None)
            return "🗑 The channel post no longer exists (it was deleted), so the post was marked as deleted."
        log.warning("Live edit of post %s failed: %s", post["token"], getattr(e, "ID", e))
        return friendly(e)


async def live_caption(client: Client, post: dict, channel: dict) -> str | None:
    return await _live(post, lambda: client.edit_message_caption(
        channel["tg_chat_id"], post["message_id"], full_caption(post, channel),
        reply_markup=post_markup(channel, post.get("download_url")),
    ))


async def live_buttons(client: Client, post: dict, channel: dict) -> str | None:
    return await _live(post, lambda: client.edit_message_reply_markup(
        channel["tg_chat_id"], post["message_id"], post_markup(channel, post.get("download_url")),
    ))


async def live_media(client: Client, post: dict, channel: dict, media_type: str, file_id: str) -> str | None:
    new_media = media.input_media(media_type, file_id, full_caption(post, channel))
    if new_media is None or post.get("media_type") == "voice":
        return ("🎙 Telegram can't swap voice messages in an existing post. "
                "Delete the post and send a new one instead.")
    return await _live(post, lambda: client.edit_message_media(
        channel["tg_chat_id"], post["message_id"], new_media,
        reply_markup=post_markup(channel, post.get("download_url")),
    ))


async def delete_live(client: Client, post: dict) -> None:
    """Delete the channel message. A message that is already gone counts as deleted."""
    try:
        await client.delete_messages(post["channel_id"], post["message_id"])
    except RPCError as e:
        if not is_message_gone(e):
            raise
