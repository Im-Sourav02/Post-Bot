"""Flow 2: My Posts — list per channel, delete/cancel, and the edit panel that updates the live post."""
from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import CallbackQuery, Message

from bot import config
from bot.db import channels, posts, states
from bot.handlers.router import callback, step
from bot.keyboards import NUMBERS, btn, channel_grid, markup, nav, only_nav
from bot.keyboards import posts as post_kb
from bot.services import media, poster, screens, ui
from bot.services.errors import friendly
from bot.services.formatting import caption_overflow, esc, message_html, normalize_url, snippet, too_long_text
from bot.services.timeutil import fmt, now_local_str, now_utc, parse_local

PICK_TEXT = "📢 <b>Select the channel whose posts you want to edit:</b>"
FILTER_NAMES = {"a": "All posts", "s": "Scheduled posts", "t": "Sent posts"}
NOT_EDITABLE = {
    posts.DELETED: "🗑 This post was deleted, so it can't be edited.",
    posts.CANCELLED: "❌ This post was cancelled, so it can't be edited.",
    posts.SENDING: "⏳ This post is being sent right now. Try again in a moment.",
    posts.DELETING: "⏳ This post is being deleted right now.",
    posts.DRAFT: "📝 This post hasn't been finished yet.",
}


# ---------- channel picker & list ----------

async def show_picker(client: Client, chat_id: int, page: int = 0, cq_msg: Message | None = None) -> None:
    chs = await channels.list_all()
    if not chs:
        await ui.show(client, chat_id, "📭 No channels yet.\nThe owner can add one with /addchannel.",
                      only_nav("menu"), cq_msg=cq_msg)
        return
    await ui.show(client, chat_id, PICK_TEXT, channel_grid(chs, page, "ml", "mp", "menu"), cq_msg=cq_msg)


async def myposts_cmd(client: Client, msg: Message) -> None:
    await states.clear(msg.from_user.id)
    await show_picker(client, msg.chat.id)


@callback("mp")
async def pick_cb(client: Client, cq: CallbackQuery, args: list[str]):
    await show_picker(client, cq.message.chat.id, int(args[0]) if args else 0, cq_msg=cq.message)


async def _show_list(client: Client, cq: CallbackQuery, chat: int, flt: str, page: int):
    channel = await channels.get(chat)
    if not channel:
        return "📢 This channel no longer exists.", True
    flt = flt if flt in FILTER_NAMES else "a"
    docs, more = await posts.list_for_channel(chat, flt, page, config.POSTS_PER_PAGE)
    if not docs and page > 0:
        return await _show_list(client, cq, chat, flt, page - 1)

    lines = [
        "📩 <b>Select the post you want to edit</b>",
        "<i>If you delete a scheduled post from here that has not yet been sent, it will not be sent.</i>",
        "",
        f"📢 {esc(channel['title'])} • {FILTER_NAMES[flt]} • Page {page + 1}",
        "",
    ]
    for i, p in enumerate(docs):
        when = f"🗓 {fmt(p.get('send_at'))}" if p["status"] == posts.SCHEDULED else f"📤 {fmt(p.get('sent_at'))}"
        lines.append(f"{NUMBERS[i]} {esc(snippet(p.get('caption_html')))}\n      <i>{when}</i>")
    if not docs:
        lines.append("📭 No posts here yet.")

    def flt_btn(key: str, label: str):
        active = flt == key
        return btn(("✅ " if active else "") + label, "ml", chat, "a" if active else key, 0)

    rows = [[flt_btn("s", "🗓 Scheduled posts"), flt_btn("t", "📤 Sent posts")]]
    pair = []
    for i, p in enumerate(docs):
        pair += [btn(NUMBERS[i], "ed", p["token"]), btn("🗑", "dl", p["token"], flt, page)]
        if len(pair) == 4:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([
        btn("⬅️", "ml", chat, flt, page - 1) if page > 0 else btn("🚫", "noop"),
        btn("➡️", "ml", chat, flt, page + 1) if more else btn("🚫", "noop"),
    ])
    rows.append(nav("mp:0"))
    await ui.show(client, cq.message.chat.id, "\n".join(lines), markup(rows), cq_msg=cq.message)
    return None


@callback("ml")
async def list_cb(client: Client, cq: CallbackQuery, args: list[str]):
    chat = int(args[0])
    flt = args[1] if len(args) > 1 else "a"
    page = int(args[2]) if len(args) > 2 else 0
    return await _show_list(client, cq, chat, flt, max(page, 0))


@callback("dl")
async def delete_confirm_cb(client: Client, cq: CallbackQuery, args: list[str]):
    token, flt, page = args[0], args[1], int(args[2])
    post = await posts.get(token)
    if not post or post["status"] not in (posts.SCHEDULED, posts.SENT):
        return "ℹ️ This post is already gone.", True
    channel = await channels.get(post["channel_id"])
    title = esc(channel["title"]) if channel else "the channel"
    if post["status"] == posts.SCHEDULED:
        effect = f"It is scheduled for {fmt(post.get('send_at'))} and <b>will not be sent</b>."
    else:
        effect = f"It will be <b>deleted from 📢 {title}</b>."
    text = f"🗑 <b>Delete this post?</b>\n\n“{esc(snippet(post.get('caption_html'), 12, 80))}”\n\n{effect}"
    kb = markup([[btn("✅ Yes, delete", "dly", token, flt, page)], nav(f"ml:{post['channel_id']}:{flt}:{page}")])
    await ui.show(client, cq.message.chat.id, text, kb, cq_msg=cq.message)


@callback("dly")
async def delete_cb(client: Client, cq: CallbackQuery, args: list[str]):
    token, flt, page = args[0], args[1], int(args[2])
    post = await posts.get(token)
    if not post:
        return "ℹ️ This post is already gone.", True
    toast = "ℹ️ This post is already gone."
    if await posts.claim(token, posts.SCHEDULED, posts.CANCELLED):
        toast = "🗑 Scheduled post cancelled. It will not be sent."
    elif claimed := await posts.claim(token, posts.SENT, posts.DELETING):
        try:
            await poster.delete_live(client, claimed)
        except (FloodWait, RPCError) as e:
            await posts.update(token, status=posts.SENT)
            return friendly(e), True
        await posts.update(token, status=posts.DELETED, deleted_at=now_utc())
        toast = "🗑 Post deleted from the channel."
    await _show_list(client, cq, post["channel_id"], flt, page)
    return toast


# ---------- edit panel ----------

async def show_panel(client: Client, uid: int, post: dict, note: str = "", *, cq_msg=None, previous=None) -> None:
    channel = await channels.get(post["channel_id"])
    text = screens.edit_panel(post, channel, client.me.username)
    await ui.render(client, uid, (note + "\n\n" if note else "") + text, post_kb.edit_panel(post, channel),
                    cq_msg=cq_msg, previous=previous)


async def _editable(token: str) -> tuple[dict | None, tuple | None]:
    post = await posts.get(token)
    if not post:
        return None, ("❌ This post no longer exists.", True)
    if post["status"] in NOT_EDITABLE:
        return None, (NOT_EDITABLE[post["status"]], True)
    return post, None


@callback("ed")
async def edit_cb(client: Client, cq: CallbackQuery, args: list[str]):
    post = await posts.get(args[0])
    if not post:
        return "❌ This post no longer exists.", True
    await show_panel(client, cq.from_user.id, post, cq_msg=cq.message)


@callback("sv")
async def see_cb(client: Client, cq: CallbackQuery, args: list[str]):
    token, part = args[0], args[1]
    post = await posts.get(token)
    if not post:
        return "❌ This post no longer exists.", True
    channel = await poster.channel_for(post)
    uid = cq.from_user.id
    back = nav(f"ed:{token}")
    if part == "m":
        kb = post_kb.post_markup(channel, post.get("download_url"), extra_rows=[back])
        await ui.show_media(client, uid, post["media_type"], post["file_id"], poster.full_caption(post, channel), kb,
                            cq_msg=cq.message)
    elif part == "c":
        text = "🔤 <b>Caption preview</b> (with signature):\n\n" + (poster.full_caption(post, channel) or "—")
        await ui.show(client, uid, text, markup([back]), cq_msg=cq.message)
    else:
        text = (
            "⌨️ <b>Buttons preview</b>\n\n"
            f"💎 Premium: {esc(channel.get('premium_url') or '— not set')}\n"
            f"📁 Backup: {esc(channel.get('backup_url') or '— not set')}\n"
            f"🔴 Download: {esc(post.get('download_url') or '— not set')}"
        )
        kb = post_kb.post_markup(channel, post.get("download_url"), extra_rows=[back])
        await ui.show(client, uid, text, kb, cq_msg=cq.message)


async def _prompt(client, cq, post, step_name: str, text: str, extra_rows=()) -> None:
    kb = markup([*extra_rows, nav(f"ed:{post['token']}")])
    m = await ui.show(client, cq.message.chat.id, text, kb, cq_msg=cq.message)
    await states.set(cq.from_user.id, step_name, {"token": post["token"], "msg": m.id})


async def _reprompt(client, msg, data: dict, step_name: str, text: str) -> None:
    m = await ui.respond(client, msg.chat.id, text, only_nav(f"ed:{data['token']}"), previous=data.get("msg"))
    await states.set(msg.from_user.id, step_name, {**data, "msg": m.id})


async def _step_post(msg: Message, data: dict) -> dict | None:
    post, error = await _editable(data["token"])
    if error:
        await states.clear(msg.from_user.id)
        await msg.reply(error[0])
    return post


@callback("em")
async def edit_media_cb(client: Client, cq: CallbackQuery, args: list[str]):
    post, error = await _editable(args[0])
    if error:
        return error
    if post["status"] == posts.SENT and post["media_type"] == "voice":
        return "🎙 Telegram can't swap the media of a voice message post. Delete it and send a new post.", True
    await _prompt(client, cq, post, "ed_media",
                  "🖼 <b>Send the new media for this post.</b>\n\n"
                  "Photo, video, GIF, file or audio. The caption and buttons stay the same.")


@step("ed_media")
async def edit_media_step(client: Client, msg: Message, state: dict) -> None:
    data = state["data"]
    post = await _step_post(msg, data)
    if not post:
        return
    try:
        media_type, file_id = media.extract(msg)
    except media.UnsupportedMedia as e:
        await msg.reply(e.text)
        return
    if post["status"] == posts.SENT:
        channel = await poster.channel_for(post)
        error = await poster.live_media(client, post, channel, media_type, file_id)
        if error:
            await states.clear(msg.from_user.id)
            await show_panel(client, msg.chat.id, await posts.get(post["token"]), error, previous=data.get("msg"))
            return
    post = await posts.update(post["token"], media_type=media_type, file_id=file_id)
    await states.clear(msg.from_user.id)
    await show_panel(client, msg.chat.id, post, "✅ Media updated.", previous=data.get("msg"))


@callback("ec")
async def edit_caption_cb(client: Client, cq: CallbackQuery, args: list[str]):
    post, error = await _editable(args[0])
    if error:
        return error
    await _prompt(client, cq, post, "ed_caption",
                  "🔤 <b>Send the new caption for this post.</b>\n"
                  "The channel signature is added automatically.\n\n"
                  f"<b>Current caption:</b>\n{post.get('caption_html') or '—'}")


@step("ed_caption")
async def edit_caption_step(client: Client, msg: Message, state: dict) -> None:
    data = state["data"]
    post = await _step_post(msg, data)
    if not post:
        return
    caption_html = message_html(msg).strip()
    if not caption_html:
        await _reprompt(client, msg, data, "ed_caption", "✍️ Please send the new caption as text.")
        return
    channel = await poster.channel_for(post)
    if caption_overflow(caption_html, channel.get("signature")):
        await _reprompt(client, msg, data, "ed_caption", too_long_text(caption_html, channel.get("signature")))
        return
    updated = {**post, "caption_html": caption_html}
    if post["status"] == posts.SENT:
        error = await poster.live_caption(client, updated, channel)
        if error:
            await states.clear(msg.from_user.id)
            await show_panel(client, msg.chat.id, await posts.get(post["token"]), error, previous=data.get("msg"))
            return
    post = await posts.update(post["token"], caption_html=caption_html)
    await states.clear(msg.from_user.id)
    await show_panel(client, msg.chat.id, post, "✅ Caption updated.", previous=data.get("msg"))


@callback("eb")
async def edit_buttons_cb(client: Client, cq: CallbackQuery, args: list[str]):
    post, error = await _editable(args[0])
    if error:
        return error
    await _prompt(client, cq, post, "ed_link",
                  "⌨️ <b>Send the new Download link for this post.</b>\n\n"
                  f"Current: {esc(post.get('download_url') or '—')}\n\n"
                  "💎 Premium and 📁 Backup are refreshed from the channel settings at the same time.",
                  extra_rows=[[btn("🔄 Only refresh Premium/Backup", "ebr", post["token"])]])


@step("ed_link")
async def edit_link_step(client: Client, msg: Message, state: dict) -> None:
    data = state["data"]
    post = await _step_post(msg, data)
    if not post:
        return
    url = normalize_url(msg.text)
    if not url:
        await _reprompt(client, msg, data, "ed_link",
                        "❌ That doesn't look like a valid link. Send a URL such as "
                        "<code>https://t.me/SomeBot?start=abc</code>.")
        return
    updated = {**post, "download_url": url}
    if post["status"] == posts.SENT:
        error = await poster.live_buttons(client, updated, await poster.channel_for(post))
        if error:
            await states.clear(msg.from_user.id)
            await show_panel(client, msg.chat.id, await posts.get(post["token"]), error, previous=data.get("msg"))
            return
    post = await posts.update(post["token"], download_url=url)
    await states.clear(msg.from_user.id)
    await show_panel(client, msg.chat.id, post, "✅ Buttons updated.", previous=data.get("msg"))


@callback("ebr")
async def refresh_buttons_cb(client: Client, cq: CallbackQuery, args: list[str]):
    post, error = await _editable(args[0])
    if error:
        return error
    note = "✅ Buttons will use the current settings when the post is sent."
    if post["status"] == posts.SENT:
        failure = await poster.live_buttons(client, post, await poster.channel_for(post))
        note = failure or "✅ Premium/Backup buttons refreshed on the channel post."
    await show_panel(client, cq.from_user.id, await posts.get(post["token"]), note, cq_msg=cq.message)


@callback("sd")
async def schedule_delete_cb(client: Client, cq: CallbackQuery, args: list[str]):
    post, error = await _editable(args[0])
    if error:
        return error
    current = ""
    extra = []
    if post.get("delete_at") or post.get("delete_delay"):
        when = fmt(post["delete_at"]) if post.get("delete_at") else "after sending (copied delay)"
        current = f"\n\n🗑 Current deletion: <b>{when}</b>"
        extra = [[btn("❌ Remove deletion schedule", "sdx", post["token"])]]
    await _prompt(client, cq, post, "ed_delete",
                  "🗑 <b>Schedule deletion</b>\n\n" + screens.date_prompt("when this post should be deleted",
                                                                         now_local_str()) + current,
                  extra_rows=extra)


@step("ed_delete")
async def schedule_delete_step(client: Client, msg: Message, state: dict) -> None:
    data = state["data"]
    post = await _step_post(msg, data)
    if not post:
        return
    when = parse_local(msg.text or "")
    if when is None:
        await _reprompt(client, msg, data, "ed_delete",
                        "❌ Invalid format. Use <code>DD/MM/YYYY HH:MM</code>, e.g. <code>25/12/2026 18:30</code>.")
        return
    if when <= now_utc():
        await _reprompt(client, msg, data, "ed_delete", "❌ That time is in the past. Please send a future time.")
        return
    if post["status"] == posts.SCHEDULED and post.get("send_at") and when <= post["send_at"]:
        await _reprompt(client, msg, data, "ed_delete",
                        f"❌ The deletion time must be after the sending time ({fmt(post['send_at'])}).")
        return
    post = await posts.update(post["token"], delete_at=when, delete_delay=None)
    await states.clear(msg.from_user.id)
    await show_panel(client, msg.chat.id, post, f"🗑 The post will be deleted on <b>{fmt(when)}</b>.",
                     previous=data.get("msg"))


@callback("sdx")
async def remove_delete_cb(client: Client, cq: CallbackQuery, args: list[str]):
    post, error = await _editable(args[0])
    if error:
        return error
    post = await posts.update(post["token"], delete_at=None, delete_delay=None)
    await show_panel(client, cq.from_user.id, post, "✅ Deletion schedule removed.", cq_msg=cq.message)
