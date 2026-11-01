"""Flow 3: per-channel settings — signature, backup link, premium link, forwarding."""
from pyrogram import Client
from pyrogram.types import CallbackQuery, Message

from bot import config
from bot.db import channels, states
from bot.handlers.router import callback, step
from bot.keyboards import btn, channel_grid, markup, nav, only_nav
from bot.services import ui
from bot.services.formatting import esc, html_message_html, normalize_url, tg_len

PICK_TEXT = "⚙️ <b>Select the channel you want to edit the settings for:</b>"
OPTIONS = {
    "sig": ("✍️ Signature", "signature",
            "The signature is added at the end of every post caption in this channel."),
    "bak": ("🗂 Backup", "backup_url",
            "Link of the 📁 Backup button (first row, next to 💎 Premium)."),
    "pre": ("⭐ Premium", "premium_url",
            "Link of the 💎 Premium button (first row, next to 📁 Backup)."),
}


async def show_picker(client: Client, chat_id: int, page: int = 0, cq_msg: Message | None = None) -> None:
    chs = await channels.list_all()
    if not chs:
        await ui.show(client, chat_id, "📭 No channels yet.\nThe owner can add one with /addchannel.",
                      only_nav("menu"), cq_msg=cq_msg)
        return
    await ui.show(client, chat_id, PICK_TEXT, channel_grid(chs, page, "stc", "st", "menu"), cq_msg=cq_msg)


async def settings_cmd(client: Client, msg: Message) -> None:
    await states.clear(msg.from_user.id)
    await show_picker(client, msg.chat.id)


@callback("st")
async def pick_cb(client: Client, cq: CallbackQuery, args: list[str]):
    await show_picker(client, cq.message.chat.id, int(args[0]) if args else 0, cq_msg=cq.message)


@callback("stc")
async def channel_cb(client: Client, cq: CallbackQuery, args: list[str]):
    chat = int(args[0])
    channel = await channels.get(chat)
    if not channel:
        return "📢 This channel no longer exists.", True
    text = (f"⚙️ <b>Post Settings for {esc(channel['title'])}</b>\n"
            "Select the option you want to change..")
    kb = markup([
        [btn("✍️ Signature", "so", chat, "sig"), btn("🗂 Backup", "so", chat, "bak")],
        [btn("⭐ Premium", "so", chat, "pre"), btn("↪️ Forwarding", "so", chat, "fwd")],
        nav("st:0"),
    ])
    await ui.show(client, cq.message.chat.id, text, kb, cq_msg=cq.message)


def _option_screen(channel: dict, key: str) -> tuple[str, object]:
    chat = channel["tg_chat_id"]
    title = esc(channel["title"])
    back = nav(f"stc:{chat}")
    if key == "fwd":
        protected = bool(channel.get("protect_content"))
        state = ("🚫 <b>Restricted</b> — posts are sent with protected content, members can't forward or save them."
                 if protected else
                 "✅ <b>Allowed</b> — members can forward and save posts.")
        text = f"↪️ <b>Forwarding for {title}</b>\n\n{state}\n\nApplies to posts sent from now on."
        toggle = "✅ Allow forwarding" if protected else "🚫 Restrict forwarding"
        return text, markup([[btn(toggle, "sf", chat)], back])

    label, field, about = OPTIONS[key]
    value = channel.get(field)
    if key == "sig":
        shown = value or "<i>— not set —</i>"
    else:
        shown = esc(value) if value else "<i>— not set —</i>"
    text = f"{label} <b>for {title}</b>\n\n{about}\n\n<b>Current value:</b>\n{shown}"
    if value:
        rows = [[btn("✏️ Edit", "ss", chat, key), btn("🗑 Remove", "sr", chat, key)]]
    else:
        rows = [[btn("➕ Set", "ss", chat, key)]]
    return text, markup([*rows, back])


@callback("so")
async def option_cb(client: Client, cq: CallbackQuery, args: list[str]):
    channel = await channels.get(int(args[0]))
    if not channel:
        return "📢 This channel no longer exists.", True
    text, kb = _option_screen(channel, args[1])
    await ui.show(client, cq.message.chat.id, text, kb, cq_msg=cq.message)


@callback("ss")
async def set_cb(client: Client, cq: CallbackQuery, args: list[str]):
    chat, key = int(args[0]), args[1]
    channel = await channels.get(chat)
    if not channel or key not in OPTIONS:
        return "📢 This channel no longer exists.", True
    label = OPTIONS[key][0]
    if key == "sig":
        text = (f"{label}\n\nSend the new signature for <b>{esc(channel['title'])}</b>.\n"
                "Formatting (bold, links, etc.) is kept, and you can also type HTML, e.g. "
                "<code>&lt;b&gt;Join&lt;/b&gt; &lt;a href=\"https://t.me/SomeChannel\"&gt;here&lt;/a&gt;</code>")
    else:
        text = (f"{label}\n\nSend the new link for <b>{esc(channel['title'])}</b>.\n"
                "Example: <code>https://t.me/SomeChannel</code>")
    m = await ui.show(client, cq.message.chat.id, text, only_nav(f"so:{chat}:{key}"), cq_msg=cq.message)
    await states.set(cq.from_user.id, "set_value", {"chat": chat, "key": key, "msg": m.id})


@step("set_value")
async def set_value_step(client: Client, msg: Message, state: dict) -> None:
    data = state["data"]
    chat, key = data["chat"], data["key"]
    uid = msg.from_user.id
    channel = await channels.get(chat)
    if not channel:
        await states.clear(uid)
        await msg.reply("📢 This channel no longer exists.")
        return
    field = OPTIONS[key][1]
    if key == "sig":
        value = await html_message_html(msg)
        error = None
        if value is None:
            error = "❌ Couldn't read the HTML in that signature. Check the tags and send it again."
        elif not (value := value.strip()):
            error = "✍️ Please send the signature as text."
        elif tg_len(value) > config.CAPTION_LIMIT - 2:
            error = f"⚠️ The signature is too long ({tg_len(value)} characters). Please send a shorter one."
    else:
        value = normalize_url(msg.text)
        error = None if value else ("❌ That doesn't look like a valid link. "
                                    "Send a URL such as <code>https://t.me/SomeChannel</code>.")
    if error:
        m = await ui.respond(client, msg.chat.id, error, only_nav(f"so:{chat}:{key}"), previous=data.get("msg"))
        await states.set(uid, "set_value", {**data, "msg": m.id})
        return
    await channels.set_fields(chat, **{field: value})
    await states.clear(uid)
    text, kb = _option_screen(await channels.get(chat), key)
    await ui.respond(client, msg.chat.id, "✅ Saved.\n\n" + text, kb, previous=data.get("msg"))


@callback("sr")
async def remove_cb(client: Client, cq: CallbackQuery, args: list[str]):
    chat, key = int(args[0]), args[1]
    if key not in OPTIONS or not await channels.get(chat):
        return "📢 This channel no longer exists.", True
    await channels.set_fields(chat, **{OPTIONS[key][1]: "" if key == "sig" else None})
    text, kb = _option_screen(await channels.get(chat), key)
    await ui.show(client, cq.message.chat.id, text, kb, cq_msg=cq.message)
    return "🗑 Removed."


@callback("sf")
async def toggle_forwarding_cb(client: Client, cq: CallbackQuery, args: list[str]):
    chat = int(args[0])
    channel = await channels.get(chat)
    if not channel:
        return "📢 This channel no longer exists.", True
    await channels.set_fields(chat, protect_content=not channel.get("protect_content"))
    text, kb = _option_screen(await channels.get(chat), "fwd")
    await ui.show(client, cq.message.chat.id, text, kb, cq_msg=cq.message)
    return "✅ Updated."
