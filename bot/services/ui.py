"""Screen rendering: edit the current bot message in place whenever Telegram allows it."""
import logging

from pyrogram import Client
from pyrogram.enums import MessageMediaType
from pyrogram.errors import RPCError
from pyrogram.types import LinkPreviewOptions, Message

from bot.services import media
from bot.services.errors import is_not_modified

log = logging.getLogger(__name__)

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def _is_text(msg: Message) -> bool:
    return msg.media is None or msg.media == MessageMediaType.WEB_PAGE


async def safe_delete(msg: Message | None) -> None:
    if msg is None:
        return
    try:
        await msg.delete()
    except RPCError:
        pass


async def strip_markup(client: Client, chat_id: int, message_id: int | None) -> None:
    """Remove buttons from an old screen so stale taps can't be made."""
    if not message_id:
        return
    try:
        await client.edit_message_reply_markup(chat_id, message_id, None)
    except RPCError:
        pass


async def show(client: Client, chat_id: int, text: str, reply_markup=None, *, cq_msg: Message | None = None) -> Message:
    """Show a text screen. Edits cq_msg if it is a text message, otherwise replaces it."""
    if cq_msg is not None:
        if _is_text(cq_msg):
            try:
                return await client.edit_message_text(
                    chat_id, cq_msg.id, text, reply_markup=reply_markup, link_preview_options=NO_PREVIEW
                )
            except RPCError as e:
                if is_not_modified(e):
                    return cq_msg
                log.debug("edit_message_text failed (%s), sending a new message", getattr(e, "ID", e))
        await safe_delete(cq_msg)
    return await client.send_message(chat_id, text, reply_markup=reply_markup, link_preview_options=NO_PREVIEW)


async def show_media(
    client: Client,
    chat_id: int,
    media_type: str,
    file_id: str,
    caption: str,
    reply_markup=None,
    *,
    cq_msg: Message | None = None,
) -> Message:
    """Show a media screen (e.g. a post preview), replacing cq_msg."""
    await safe_delete(cq_msg)
    return await media.send(client, chat_id, media_type, file_id, caption, reply_markup)


async def respond(client: Client, chat_id: int, text: str, reply_markup=None, *, previous: int | None = None) -> Message:
    """Answer a user's input with a new screen, disabling the previous screen's buttons."""
    await strip_markup(client, chat_id, previous)
    return await client.send_message(chat_id, text, reply_markup=reply_markup, link_preview_options=NO_PREVIEW)


async def render(
    client: Client,
    chat_id: int,
    text: str,
    reply_markup=None,
    *,
    cq_msg: Message | None = None,
    previous: int | None = None,
) -> Message:
    """Edit the tapped screen (button press) or answer with a new one (typed input)."""
    if cq_msg is not None:
        return await show(client, chat_id, text, reply_markup, cq_msg=cq_msg)
    return await respond(client, chat_id, text, reply_markup, previous=previous)
