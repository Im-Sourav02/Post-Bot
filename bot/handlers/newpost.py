"""Flow 1: New Post — channel → media → caption → download link → preview → send / schedule."""
from datetime import datetime, timezone

from pyrogram import Client
from pyrogram.types import CallbackQuery, Message

from bot import config
from bot.db import channels, posts, states
from bot.handlers.router import callback, step
from bot.handlers.start import show_menu
from bot.keyboards import btn, channel_grid, markup, nav, only_nav
from bot.keyboards.posts import actions, post_markup
from bot.services import media, poster, ui
from bot.services.formatting import caption_overflow, esc, message_html, normalize_url, too_long_text
from bot.services.screens import date_prompt, post_sent
from bot.services.timeutil import fmt, now_local_str, now_utc, parse_local

NO_CHANNELS = "📭 No channels yet.\nThe owner can add one with /addchannel."
PICK_TEXT = "📢 <b>Select the channel you want to make the post for:</b>"
MEDIA_TEXT = (
    "📢 <b>{title}</b>\n\n"
    "Send the post message or media.\n"
    "Allowed media: photos, videos, albums, files, stickers, GIFs, audio, voice messages, round videos.\n\n"
    "💡 To attach a media under the post send it here."
)
CAPTION_TEXT = "Send the caption of the media. Press 'Attach media' if you want to view the media under the caption."
LINK_TEXT = (
    "🔗 <b>Send the Download link for the post.</b>\n\n"
    "Example: <code>https://t.me/SomeBot?start=abc</code>"
)
BAD_LINK = "❌ That doesn't look like a valid link. It must be a URL such as <code>https://t.me/SomeBot?start=abc</code>.\n\n"
GONE = ("ℹ️ This post was already sent, scheduled or cancelled.", True)


async def show_picker(client: Client, chat_id: int, page: int = 0, cq_msg: Message | None = None) -> None:
    chs = await channels.list_all()
    if not chs:
        await ui.show(client, chat_id, NO_CHANNELS, only_nav("menu"), cq_msg=cq_msg)
        return
    await ui.show(client, chat_id, PICK_TEXT, channel_grid(chs, page, "npc", "np", "menu"), cq_msg=cq_msg)


async def newpost_cmd(client: Client, msg: Message) -> None:
    await states.clear(msg.from_user.id)
    await show_picker(client, msg.chat.id)


@callback("np")
async def pick_cb(client: Client, cq: CallbackQuery, args: list[str]):
    await show_picker(client, cq.message.chat.id, int(args[0]) if args else 0, cq_msg=cq.message)


async def _ask_media(client, uid, channel, token=None, *, cq_msg=None, previous=None):
    m = await ui.render(client, uid, MEDIA_TEXT.format(title=esc(channel["title"])), only_nav("np:0"),
                        cq_msg=cq_msg, previous=previous)
    await states.set(uid, "np_media", {"chat": channel["tg_chat_id"], "token": token, "msg": m.id})


def _caption_kb(token: str):
    return markup([
        [btn("🖼 Attach media", "npa", token), btn("❌ NO", "npx", token)],
        nav(f"npb:{token}:m"),
    ])


async def _ask_caption(client, uid, post, note: str = "", *, cq_msg=None, previous=None):
    text = (note + "\n\n" if note else "") + CAPTION_TEXT
    m = await ui.render(client, uid, text, _caption_kb(post["token"]), cq_msg=cq_msg, previous=previous)
    await states.set(uid, "np_caption", {"token": post["token"], "msg": m.id})


async def _ask_link(client, uid, post, note: str = "", *, cq_msg=None, previous=None):
    m = await ui.render(client, uid, note + LINK_TEXT, only_nav(f"npb:{post['token']}:c"),
                        cq_msg=cq_msg, previous=previous)
    await states.set(uid, "np_link", {"token": post["token"], "msg": m.id})


async def _show_preview(client, uid, post, *, cq_msg=None, previous=None):
    channel = await poster.channel_for(post)
    t = post["token"]
    kb = post_markup(channel, post.get("download_url"), extra_rows=[
        [btn("✅ Send Now", "nsn", t), btn("🕒 Schedule Sending", "nss", t)],
        nav(f"npb:{t}:l"),
    ])
    await ui.strip_markup(client, uid, previous)
    await ui.show_media(client, uid, post["media_type"], post["file_id"], poster.full_caption(post, channel), kb,
                        cq_msg=cq_msg)
    await states.clear(uid)


async def _accept_caption(client, uid, post, caption_html: str, previous: int | None):
    channel = await poster.channel_for(post)
    if caption_overflow(caption_html, channel.get("signature")):
        await _ask_caption(client, uid, post, too_long_text(caption_html, channel.get("signature")),
                           previous=previous)
        return
    post = await posts.update(post["token"], caption_html=caption_html)
    await _ask_link(client, uid, post, previous=previous)


async def _accept_media(client, msg: Message, data: dict) -> None:
    uid = msg.from_user.id
    try:
        media_type, file_id = media.extract(msg)
    except media.UnsupportedMedia as e:
        await msg.reply(e.text)
        return
    post = await posts.get(data["token"]) if data.get("token") else None
    if post and post["status"] == posts.DRAFT:
        post = await posts.update(post["token"], media_type=media_type, file_id=file_id)
    else:
        chat = data.get("chat") or (post or {}).get("channel_id")
        if not await channels.get(chat):
            await states.clear(uid)
            await msg.reply("📢 This channel was removed from the bot.")
            return
        post = await posts.create(chat, uid, media_type=media_type, file_id=file_id)
    if msg.caption:
        await _accept_caption(client, uid, post, message_html(msg), data.get("msg"))
    else:
        await _ask_caption(client, uid, post, previous=data.get("msg"))


@callback("npc")
async def channel_cb(client: Client, cq: CallbackQuery, args: list[str]):
    channel = await channels.get(int(args[0]))
    if not channel:
        return "📢 This channel no longer exists.", True
    await _ask_media(client, cq.from_user.id, channel, cq_msg=cq.message)


@step("np_media")
async def media_step(client: Client, msg: Message, state: dict) -> None:
    await _accept_media(client, msg, state["data"])


@step("np_caption")
async def caption_step(client: Client, msg: Message, state: dict) -> None:
    data = state["data"]
    if msg.media:
        await _accept_media(client, msg, data)
        return
    post = await posts.get(data["token"])
    if not post or post["status"] != posts.DRAFT:
        await states.clear(msg.from_user.id)
        await msg.reply(GONE[0])
        return
    caption_html = message_html(msg).strip()
    if not caption_html:
        await _ask_caption(client, msg.from_user.id, post, "✍️ Please send the caption as text.",
                           previous=data.get("msg"))
        return
    await _accept_caption(client, msg.from_user.id, post, caption_html, data.get("msg"))


@step("np_link")
async def link_step(client: Client, msg: Message, state: dict) -> None:
    data = state["data"]
    uid = msg.from_user.id
    post = await posts.get(data["token"])
    if not post or post["status"] != posts.DRAFT:
        await states.clear(uid)
        await msg.reply(GONE[0])
        return
    url = normalize_url(msg.text)
    if not url:
        await _ask_link(client, uid, post, BAD_LINK, previous=data.get("msg"))
        return
    post = await posts.update(post["token"], download_url=url)
    await _show_preview(client, uid, post, previous=data.get("msg"))


async def _draft(token: str) -> dict | None:
    post = await posts.get(token)
    return post if post and post["status"] == posts.DRAFT else None


@callback("npb")
async def back_cb(client: Client, cq: CallbackQuery, args: list[str]):
    token, target = args[0], args[1]
    post = await _draft(token)
    if not post:
        return GONE
    uid = cq.from_user.id
    if target == "m":
        channel = await poster.channel_for(post)
        await _ask_media(client, uid, channel, token, cq_msg=cq.message)
    elif target == "c":
        await _ask_caption(client, uid, post, cq_msg=cq.message)
    elif target == "l":
        await _ask_link(client, uid, post, cq_msg=cq.message)
    else:
        await _show_preview(client, uid, post, cq_msg=cq.message)


@callback("npa")
async def attach_cb(client: Client, cq: CallbackQuery, args: list[str]):
    post = await _draft(args[0])
    if not post:
        return GONE
    m = await ui.show_media(client, cq.from_user.id, post["media_type"], post["file_id"], CAPTION_TEXT,
                            _caption_kb(post["token"]), cq_msg=cq.message)
    await states.set(cq.from_user.id, "np_caption", {"token": post["token"], "msg": m.id})


@callback("npx")
async def cancel_cb(client: Client, cq: CallbackQuery, args: list[str]):
    await posts.delete_draft(args[0])
    await show_menu(client, cq.from_user, cq.message.chat.id, cq_msg=cq.message)
    return "❌ Post cancelled."


@callback("nsn")
async def send_now_cb(client: Client, cq: CallbackQuery, args: list[str]):
    post, error = await poster.send_now(client, args[0])
    if error:
        return error, True
    channel = await channels.get(post["channel_id"])
    bot = client.me.username
    await ui.show(client, cq.message.chat.id, post_sent(post, channel, bot), actions(post, bot), cq_msg=cq.message)
    return "✅ Post sent!"


@callback("nss")
async def schedule_cb(client: Client, cq: CallbackQuery, args: list[str]):
    post = await _draft(args[0])
    if not post:
        return GONE
    m = await ui.show(client, cq.message.chat.id, date_prompt("to send the post", now_local_str()),
                      only_nav(f"npb:{post['token']}:p"), cq_msg=cq.message)
    await states.set(cq.from_user.id, "np_sched", {"token": post["token"], "msg": m.id})


@step("np_sched")
async def schedule_step(client: Client, msg: Message, state: dict) -> None:
    data = state["data"]
    uid = msg.from_user.id
    token = data["token"]
    when = parse_local(msg.text or "")
    error = None
    if when is None:
        error = "❌ Invalid format. Use <code>DD/MM/YYYY HH:MM</code>, e.g. <code>25/12/2026 18:30</code>.\n\n"
    elif when <= now_utc():
        error = "❌ That time is in the past. Please send a future date and time.\n\n"
    if error:
        m = await ui.respond(client, uid, error + date_prompt("to send the post", now_local_str()),
                             only_nav(f"npb:{token}:p"), previous=data.get("msg"))
        await states.set(uid, "np_sched", {"token": token, "msg": m.id})
        return
    await states.clear(uid)
    text = (f"🗓 Schedule this post for <b>{fmt(when)}</b> ({esc(config.TIMEZONE)})?\n\n"
            "Press ✅ Confirm to schedule it.")
    kb = markup([[btn("✅ Confirm", "nsk", token, int(when.timestamp()))], nav(f"nss:{token}")])
    await ui.respond(client, uid, text, kb, previous=data.get("msg"))


@callback("nsk")
async def schedule_confirm_cb(client: Client, cq: CallbackQuery, args: list[str]):
    token = args[0]
    when = datetime.fromtimestamp(int(args[1]), timezone.utc)
    post = await _draft(token)
    if not post:
        return GONE
    if when <= now_utc():
        return "⌛ That time has already passed. Press Back and choose a new time.", True
    channel = await poster.channel_for(post)
    if caption_overflow(post.get("caption_html"), channel.get("signature")):
        await ui.show(client, cq.message.chat.id, too_long_text(post.get("caption_html"), channel.get("signature")),
                      only_nav(f"npb:{token}:c"), cq_msg=cq.message)
        return None
    post = await posts.claim(token, posts.DRAFT, posts.SCHEDULED, send_at=when)
    if not post:
        return GONE
    bot = client.me.username
    await ui.show(client, cq.message.chat.id, post_sent(post, channel, bot), actions(post, bot), cq_msg=cq.message)
    return "🗓 Post scheduled!"
