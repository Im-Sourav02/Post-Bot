"""Owner-only commands: admins and channels."""
import logging
import re

from pyrogram import Client
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import CallbackQuery, Chat, Message

from bot import config
from bot.db import admins, channels, posts, states
from bot.handlers.router import callback, step
from bot.keyboards import btn, channel_grid, markup, nav, only_nav
from bot.services import ui
from bot.services.auth import is_owner
from bot.services.errors import error_id, friendly
from bot.services.formatting import esc

log = logging.getLogger(__name__)

OWNER_ONLY = "🔒 Only the owner can use this command."
ADD_CHANNEL_PROMPT = (
    "📢 <b>Add a channel</b>\n\n"
    "1. Add this bot to the channel as an <b>admin</b> with permission to <b>post</b>, <b>edit</b> and "
    "<b>delete</b> messages.\n"
    "2. Then <b>forward any message</b> from the channel here, or send its <code>@username</code> or ID "
    "(e.g. <code>-1001234567890</code>)."
)


# ---------- admins ----------

async def _user_label(client: Client, user_id: int) -> str:
    try:
        user = await client.get_users(user_id)
        name = esc(" ".join(filter(None, [user.first_name, user.last_name])) or "user")
        return f"{name} (<code>{user_id}</code>)"
    except (RPCError, KeyError, ValueError):
        return f"<code>{user_id}</code>"


async def _target_user(client: Client, msg: Message, command: str) -> tuple[int | None, str | None]:
    usage = (f"ℹ️ Usage: <code>/{command} &lt;user_id&gt;</code>\n"
             "or reply with the command to a message from (or forwarded from) that person.")
    args = msg.command[1:]
    if args:
        raw = args[0].strip()
        if re.fullmatch(r"-?\d+", raw):
            uid = int(raw)
            if uid <= 0:
                return None, "❌ That isn't a valid user ID (user IDs are positive numbers)."
            return uid, None
        if raw.startswith("@"):
            try:
                user = await client.get_users(raw)
            except (RPCError, KeyError, ValueError):
                return None, f"❌ No Telegram user found for {esc(raw)}."
            if user.is_bot:
                return None, "❌ Bots can't be admins."
            return user.id, None
        return None, "❌ That isn't a valid user ID.\n\n" + usage

    reply = msg.reply_to_message
    if reply:
        origin = reply.forward_origin
        if origin is not None:
            user = getattr(origin, "sender_user", None)
            if user:
                return (None, "❌ Bots can't be admins.") if user.is_bot else (user.id, None)
            return None, ("❌ That person hides their account in forwarded messages, so I can't see their ID. "
                          f"Use <code>/{command} &lt;user_id&gt;</code> instead.")
        user = reply.from_user
        if user and not user.is_self and user.id != msg.from_user.id:
            return (None, "❌ Bots can't be admins.") if user.is_bot else (user.id, None)
    return None, usage


async def addadmin_cmd(client: Client, msg: Message) -> None:
    uid, error = await _target_user(client, msg, "addadmin")
    if error:
        await msg.reply(error)
        return
    if uid == config.OWNER_ID:
        await msg.reply("ℹ️ That's the owner, who already has full access.")
        return
    if uid == client.me.id:
        await msg.reply("❌ I can't make myself an admin.")
        return
    label = await _user_label(client, uid)
    if await admins.add(uid, msg.from_user.id):
        log.info("Admin %s added", uid)
        await msg.reply(f"✅ {label} is now an admin.\nThey can create and edit posts and change settings.")
    else:
        await msg.reply(f"ℹ️ {label} is already an admin.")


async def dltadmin_cmd(client: Client, msg: Message) -> None:
    uid, error = await _target_user(client, msg, "dltadmin")
    if error:
        await msg.reply(error)
        return
    if uid == config.OWNER_ID:
        await msg.reply("❌ The owner can't be removed.")
        return
    label = await _user_label(client, uid)
    if await admins.remove(uid):
        await states.clear(uid)
        log.info("Admin %s removed", uid)
        await msg.reply(f"✅ {label} is no longer an admin.")
    else:
        await msg.reply(f"❌ {label} is not an admin.")


async def admins_cmd(client: Client, msg: Message) -> None:
    rows = await admins.list_all()
    lines = [f"👑 Owner: {await _user_label(client, config.OWNER_ID)}", ""]
    if rows:
        lines.append(f"👥 <b>Admins ({len(rows)})</b>")
        for row in rows:
            lines.append(f"• {await _user_label(client, row['user_id'])}")
    else:
        lines.append("👥 No admins yet. Add one with <code>/addadmin &lt;user_id&gt;</code>.")
    await msg.reply("\n".join(lines))


async def owner_only_cmd(client: Client, msg: Message) -> None:
    await msg.reply(OWNER_ONLY)


# ---------- channels ----------

def _channel_ref(text: str) -> int | str | None:
    value = (text or "").strip()
    if re.fullmatch(r"-?\d+", value):
        num = int(value)
        return num if num < 0 else int(f"-100{num}")
    link = re.fullmatch(r"(?:https?://)?t\.me/c/(\d+)(?:/\d+)?/?", value)
    if link:
        return int(f"-100{link.group(1)}")
    link = re.fullmatch(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,})(?:/\d+)?/?", value)
    if link:
        return link.group(1)
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,}", value):
        return value.lstrip("@")
    return None


async def _verify_channel(client: Client, ref: int | str) -> tuple[Chat | None, str | None]:
    """Check the bot can post, edit and delete in the channel."""
    try:
        chat = await client.get_chat(ref)
    except FloodWait as e:
        return None, friendly(e)
    except (RPCError, KeyError, ValueError) as e:
        if error_id(e) in ("USERNAME_NOT_OCCUPIED", "USERNAME_INVALID"):
            return None, "❌ No channel found with that username."
        return None, ("❌ I can't see that channel. Add the bot to the channel as an admin first, "
                      "then try again.")
    if chat.type != ChatType.CHANNEL:
        return None, "❌ That's not a channel. Only channels are supported."
    title = esc(chat.title or "the channel")
    try:
        member = await client.get_chat_member(chat.id, "me")
    except RPCError:
        member = None
    if member is None or member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return None, (f"❌ I'm not an admin in <b>{title}</b>.\n"
                      "Add the bot as an admin with permission to post, edit and delete messages.")
    rights = member.privileges
    missing = [name for name, ok in (
        ("Post messages", rights and rights.can_post_messages),
        ("Edit messages of others", rights and rights.can_edit_messages),
        ("Delete messages of others", rights and rights.can_delete_messages),
    ) if not ok]
    if missing:
        return None, (f"⚠️ I'm an admin in <b>{title}</b> but I'm missing these permissions:\n"
                      + "\n".join(f"• {m}" for m in missing)
                      + "\n\nEnable them in the channel's admin settings and try again.")
    return chat, None


async def _add_channel(client: Client, msg: Message, ref: int | str, previous: int | None = None) -> bool:
    chat, error = await _verify_channel(client, ref)
    if error:
        m = await ui.respond(client, msg.chat.id, error + "\n\nSend another message, @username or ID to try again.",
                             only_nav("menu"), previous=previous)
        await states.set(msg.from_user.id, "add_channel", {"msg": m.id})
        return False
    is_new = await channels.upsert(chat.id, chat.title or str(chat.id), chat.username)
    await states.clear(msg.from_user.id)
    verb = "added" if is_new else "updated"
    kb = markup([[btn("⚙️ Channel settings", "stc", chat.id)], nav("menu")])
    await ui.respond(client, msg.chat.id,
                     f"✅ Channel <b>📢 {esc(chat.title or '')}</b> {verb}!\n"
                     "Open its settings to set the signature, Premium/Backup links and forwarding.",
                     kb, previous=previous)
    return True


async def addchannel_cmd(client: Client, msg: Message) -> None:
    if len(msg.command) > 1:
        ref = _channel_ref(msg.command[1])
        if ref is None:
            await msg.reply("❌ Send the channel as <code>@username</code>, a t.me link or an ID like "
                            "<code>-1001234567890</code>.")
            return
        await _add_channel(client, msg, ref)
        return
    m = await msg.reply(ADD_CHANNEL_PROMPT, reply_markup=only_nav("menu"))
    await states.set(msg.from_user.id, "add_channel", {"msg": m.id})


@step("add_channel")
async def add_channel_step(client: Client, msg: Message, state: dict) -> None:
    if not is_owner(msg.from_user.id):
        await states.clear(msg.from_user.id)
        return
    previous = state["data"].get("msg")
    origin = msg.forward_origin
    if origin is not None:
        chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
        if chat is None:
            await ui.respond(client, msg.chat.id,
                             "❌ That message wasn't forwarded from a channel. Forward a post from the channel.",
                             only_nav("menu"), previous=previous)
            await states.set(msg.from_user.id, "add_channel", {"msg": previous})
            return
        await _add_channel(client, msg, chat.id, previous)
        return
    ref = _channel_ref(msg.text or "")
    if ref is None:
        m = await ui.respond(client, msg.chat.id,
                             "❌ I couldn't read that. Forward a message from the channel, or send its "
                             "<code>@username</code> or ID.", only_nav("menu"), previous=previous)
        await states.set(msg.from_user.id, "add_channel", {"msg": m.id})
        return
    await _add_channel(client, msg, ref, previous)


async def _show_remove_picker(client: Client, chat_id: int, page: int = 0, cq_msg: Message | None = None) -> None:
    chs = await channels.list_all()
    if not chs:
        await ui.show(client, chat_id, "📭 There are no channels to remove.", only_nav("menu"), cq_msg=cq_msg)
        return
    await ui.show(client, chat_id, "🗑 <b>Select the channel you want to remove:</b>",
                  channel_grid(chs, page, "rcc", "rc", "menu"), cq_msg=cq_msg)


async def _show_remove_confirm(client: Client, chat_id: int, channel: dict, cq_msg: Message | None = None) -> None:
    text = (f"🗑 <b>Remove 📢 {esc(channel['title'])} from the bot?</b>\n\n"
            "Its scheduled posts will be cancelled. Posts already in the channel stay there.")
    kb = markup([[btn("✅ Yes, remove", "rcy", channel["tg_chat_id"])], nav("rc:0")])
    await ui.show(client, chat_id, text, kb, cq_msg=cq_msg)


async def removechannel_cmd(client: Client, msg: Message) -> None:
    await states.clear(msg.from_user.id)
    if len(msg.command) > 1:
        ref = _channel_ref(msg.command[1])
        channel = None
        if isinstance(ref, int):
            channel = await channels.get(ref)
        elif isinstance(ref, str):
            channel = await channels.find_by_username(ref)
        if not channel:
            await msg.reply("❌ That channel isn't in the bot's list. Send /removechannel to pick from the list.")
            return
        await _show_remove_confirm(client, msg.chat.id, channel)
        return
    await _show_remove_picker(client, msg.chat.id)


@callback("rc")
async def remove_pick_cb(client: Client, cq: CallbackQuery, args: list[str]):
    if not is_owner(cq.from_user.id):
        return OWNER_ONLY, True
    await _show_remove_picker(client, cq.message.chat.id, int(args[0]) if args else 0, cq_msg=cq.message)


@callback("rcc")
async def remove_confirm_cb(client: Client, cq: CallbackQuery, args: list[str]):
    if not is_owner(cq.from_user.id):
        return OWNER_ONLY, True
    channel = await channels.get(int(args[0]))
    if not channel:
        return "📢 This channel was already removed.", True
    await _show_remove_confirm(client, cq.message.chat.id, channel, cq_msg=cq.message)


@callback("rcy")
async def remove_cb(client: Client, cq: CallbackQuery, args: list[str]):
    if not is_owner(cq.from_user.id):
        return OWNER_ONLY, True
    chat = int(args[0])
    channel = await channels.get(chat)
    if not channel or not await channels.remove(chat):
        return "📢 This channel was already removed.", True
    cancelled = await posts.cancel_scheduled_for_channel(chat)
    log.info("Channel %s removed (%d scheduled posts cancelled)", chat, cancelled)
    await _show_remove_picker(client, cq.message.chat.id, cq_msg=cq.message)
    return f"✅ {channel['title']} removed." + (f" {cancelled} scheduled post(s) cancelled." if cancelled else "")
