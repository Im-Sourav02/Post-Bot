"""Post actions screen plus 'Resend post' and 'Resend identical post'."""
from pyrogram import Client
from pyrogram.types import CallbackQuery, Message

from bot.db import channels, posts, states
from bot.handlers.router import callback, step
from bot.keyboards import channel_grid, only_nav
from bot.keyboards.posts import actions
from bot.services import poster, ui
from bot.services.formatting import caption_overflow, esc, too_long_text
from bot.services.screens import date_prompt, post_sent, status_line
from bot.services.timeutil import fmt, now_local_str, now_utc, parse_local

PICK = {
    "r": "🔀 <b>Select the channel to resend this post to:</b>\n\n"
         "It will be posted there right away with that channel's links, signature and forwarding setting.",
    "i": "🔁 <b>Select the channel to send an identical copy to:</b>\n\n"
         "The sending schedule and deletion delay are copied too.",
}


@callback("pa")
async def actions_cb(client: Client, cq: CallbackQuery, args: list[str]):
    post = await posts.get(args[0])
    if not post:
        return "❌ This post no longer exists.", True
    channel = await channels.get(post["channel_id"])
    title = esc(channel["title"]) if channel else "removed channel"
    header = f"📨 <b>Post</b>\n📢 {title}\n📌 {status_line(post)}"
    bot = client.me.username
    await ui.show(client, cq.message.chat.id, post_sent(post, channel, bot, header=header), actions(post, bot),
                  cq_msg=cq.message)


@callback("rs")
async def pick_cb(client: Client, cq: CallbackQuery, args: list[str]):
    mode_origin, token, page = args[0], args[1], int(args[2])
    mode, origin = mode_origin[0], mode_origin[1]
    post = await posts.get(token)
    if not post or not post.get("file_id"):
        return "❌ This post no longer exists.", True
    back = f"ed:{token}" if origin == "e" else f"pa:{token}"
    chs = [c for c in await channels.list_all() if c["tg_chat_id"] != post["channel_id"]]
    if not chs:
        await ui.show(client, cq.message.chat.id, "📭 There are no other channels to resend this post to.",
                      only_nav(back), cq_msg=cq.message)
        return None
    kb = channel_grid(chs, page, f"rsc:{mode_origin}:{token}", f"rs:{mode_origin}:{token}", back)
    await ui.show(client, cq.message.chat.id, PICK[mode], kb, cq_msg=cq.message)


def _deletion_delay(src: dict) -> int | None:
    if src.get("delete_delay"):
        return int(src["delete_delay"])
    base = src.get("send_at") or src.get("sent_at")
    if src.get("delete_at") and base:
        return max(60, int((src["delete_at"] - base).total_seconds()))
    return None


async def _sent_screen(client, uid, post, *, cq_msg=None, previous=None):
    channel = await channels.get(post["channel_id"])
    bot = client.me.username
    await ui.render(client, uid, post_sent(post, channel, bot), actions(post, bot), cq_msg=cq_msg, previous=previous)


@callback("rsc")
async def resend_cb(client: Client, cq: CallbackQuery, args: list[str]):
    mode_origin, token, chat = args[0], args[1], int(args[2])
    mode = mode_origin[0]
    uid = cq.from_user.id
    src = await posts.get(token)
    target = await channels.get(chat)
    if not src or not src.get("file_id"):
        return "❌ This post no longer exists.", True
    if not target:
        return "📢 That channel no longer exists.", True
    back = f"rs:{mode_origin}:{token}:0"
    if caption_overflow(src.get("caption_html"), target.get("signature")):
        await ui.show(client, uid, f"📢 <b>{esc(target['title'])}</b>\n\n"
                      + too_long_text(src.get("caption_html"), target.get("signature")),
                      only_nav(back), cq_msg=cq.message)
        return None

    copy = await posts.create(
        chat, uid,
        media_type=src["media_type"], file_id=src["file_id"], caption_html=src.get("caption_html", ""),
        download_url=src.get("download_url"), source_token=token,
    )
    if mode == "i":
        delay = _deletion_delay(src)
        if delay:
            copy = await posts.update(copy["token"], delete_delay=delay)
        if src.get("send_at"):
            if src["send_at"] > now_utc():
                copy = await posts.claim(copy["token"], posts.DRAFT, posts.SCHEDULED, send_at=src["send_at"])
                await _sent_screen(client, uid, copy, cq_msg=cq.message)
                return "🗓 Post scheduled!"
            text = (f"⌛ The original sending time ({fmt(src['send_at'])}) has already passed.\n\n"
                    + date_prompt("to send this copy", now_local_str()))
            m = await ui.show(client, uid, text, only_nav(back), cq_msg=cq.message)
            await states.set(uid, "rs_time", {"token": copy["token"], "back": back, "msg": m.id})
            return None

    sent, error = await poster.send_now(client, copy["token"])
    if error:
        await posts.delete_draft(copy["token"])
        await ui.show(client, uid, error, only_nav(back), cq_msg=cq.message)
        return None
    await _sent_screen(client, uid, sent, cq_msg=cq.message)
    return "✅ Post sent!"


@step("rs_time")
async def resend_time_step(client: Client, msg: Message, state: dict) -> None:
    data = state["data"]
    uid = msg.from_user.id
    when = parse_local(msg.text or "")
    error = None
    if when is None:
        error = "❌ Invalid format. Use <code>DD/MM/YYYY HH:MM</code>.\n\n"
    elif when <= now_utc():
        error = "❌ That time is in the past. Please send a future date and time.\n\n"
    if error:
        m = await ui.respond(client, uid, error + date_prompt("to send this copy", now_local_str()),
                             only_nav(data["back"]), previous=data.get("msg"))
        await states.set(uid, "rs_time", {**data, "msg": m.id})
        return
    await states.clear(uid)
    copy = await posts.claim(data["token"], posts.DRAFT, posts.SCHEDULED, send_at=when)
    if not copy:
        await msg.reply("ℹ️ This copy was already sent or cancelled.")
        return
    await _sent_screen(client, uid, copy, previous=data.get("msg"))
