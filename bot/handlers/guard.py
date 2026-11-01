"""Runs before every other handler: anyone who isn't the owner or an admin gets one short reply."""
from pyrogram import Client, filters
from pyrogram.errors import RPCError
from pyrogram.types import CallbackQuery, Message

from bot.handlers.router import first_of_album as _first_of_album
from bot.services.auth import is_authorized

DENIED = "⛔ You are not authorized to use this bot."


async def _unauthorized(_, __, update) -> bool:
    user = getattr(update, "from_user", None)
    return not await is_authorized(user.id if user else None)


unauthorized = filters.create(_unauthorized, "Unauthorized")


async def deny_message(client: Client, msg: Message) -> None:
    if _first_of_album(msg.media_group_id):
        try:
            await msg.reply(DENIED)
        except RPCError:
            pass
    msg.stop_propagation()


async def deny_callback(client: Client, cq: CallbackQuery) -> None:
    try:
        await cq.answer(DENIED, show_alert=True)
    except RPCError:
        pass
    cq.stop_propagation()
