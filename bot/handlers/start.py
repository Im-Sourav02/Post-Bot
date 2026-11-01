from pyrogram import Client
from pyrogram.errors import RPCError
from pyrogram.types import CallbackQuery, Message, User

from bot import config
from bot.db import channels, posts, states
from bot.handlers.router import callback
from bot.keyboards import main_menu
from bot.keyboards.posts import actions, post_markup
from bot.services import media, ui
from bot.services.auth import is_owner
from bot.services.formatting import esc
from bot.services.poster import full_caption
from bot.services.screens import WELCOME, post_sent, status_line

_banner: dict[str, str] = {}

HELP = (
    "<b>Infinix Syndicate Post Bot</b>\n\n"
    "/start – main menu\n"
    "/newpost – create a new post\n"
    "/myposts – edit, schedule deletion or delete posts\n"
    "/settings – channel signature, links and forwarding\n"
    "/cancel – stop the current step"
)
OWNER_HELP = (
    "\n\n<b>Owner commands</b>\n"
    "/addadmin &lt;user_id&gt; – add an admin (or reply to their message)\n"
    "/dltadmin &lt;user_id&gt; – remove an admin (or reply to their message)\n"
    "/admins – list admins\n"
    "/addchannel – add a channel\n"
    "/removechannel – remove a channel"
)


def _name(user: User) -> str:
    return esc(f"@{user.username}" if user.username else (user.first_name or "there"))


async def show_menu(client: Client, user: User, chat_id: int, cq_msg: Message | None = None) -> Message:
    text = WELCOME.format(username=_name(user))
    kb = main_menu()
    if cq_msg is not None and cq_msg.photo and cq_msg.photo.file_unique_id == _banner.get("unique_id"):
        try:
            return await client.edit_message_caption(chat_id, cq_msg.id, text, reply_markup=kb)
        except RPCError:
            pass
    if cq_msg is not None and (cq_msg.media is None or not config.WELCOME_IMAGE.exists()):
        return await ui.show(client, chat_id, text, kb, cq_msg=cq_msg)
    if config.WELCOME_IMAGE.exists():
        await ui.safe_delete(cq_msg)
        sent = await client.send_photo(chat_id, _banner.get("file_id") or str(config.WELCOME_IMAGE),
                                       caption=text, reply_markup=kb)
        if sent.photo:
            _banner.update(file_id=sent.photo.file_id, unique_id=sent.photo.file_unique_id)
        return sent
    return await ui.show(client, chat_id, text, kb)


async def start_cmd(client: Client, msg: Message) -> None:
    await states.clear(msg.from_user.id)
    arg = msg.command[1] if len(msg.command) > 1 else ""
    if arg.startswith("resend"):
        await _shared_post(client, msg, arg.removeprefix("resend"))
        return
    await show_menu(client, msg.from_user, msg.chat.id)


async def _shared_post(client: Client, msg: Message, token: str) -> None:
    post = await posts.get(token) if token else None
    if not post or post["status"] == posts.DRAFT:
        await msg.reply("❌ This share link is invalid or the post no longer exists.", reply_markup=main_menu())
        return
    channel = await channels.get(post["channel_id"])
    bot = client.me.username
    if channel and post.get("file_id"):
        await media.send(client, msg.chat.id, post["media_type"], post["file_id"],
                         full_caption(post, channel), post_markup(channel, post.get("download_url")))
    title = esc(channel["title"]) if channel else "removed channel"
    header = f"📨 <b>Shared post</b>\n📢 {title}\n📌 {status_line(post)}"
    await ui.show(client, msg.chat.id, post_sent(post, channel, bot, header=header), actions(post, bot))


async def help_cmd(client: Client, msg: Message) -> None:
    await msg.reply(HELP + (OWNER_HELP if is_owner(msg.from_user.id) else ""))


async def cancel_cmd(client: Client, msg: Message) -> None:
    await states.clear(msg.from_user.id)
    await msg.reply("✅ Cancelled.")
    await show_menu(client, msg.from_user, msg.chat.id)


@callback("menu")
async def menu_cb(client: Client, cq: CallbackQuery, args: list[str]):
    await show_menu(client, cq.from_user, cq.message.chat.id, cq_msg=cq.message)
