from pyrogram.types import InlineKeyboardMarkup

from bot.keyboards import btn, markup, nav, url_btn
from bot.services.links import message_link, share_link, telegram_share_url
from bot.services.media import LABELS


def link_rows(channel: dict, download_url: str | None) -> list[list]:
    """Row 1: Premium + Backup (from channel settings, skipped when unset). Row 2: Download."""
    rows = []
    top = []
    if channel.get("premium_url"):
        top.append(url_btn("Pʀᴇᴍɪᴜᴍ", channel["premium_url"]))
    if channel.get("backup_url"):
        top.append(url_btn("Bᴀᴄᴋ-ᴜᴘ", channel["backup_url"]))
    if top:
        rows.append(top)
    if download_url:
        rows.append([url_btn("Wᴀᴛᴄʜ Nᴏᴡ", download_url)])
    return rows


def post_markup(channel: dict, download_url: str | None, extra_rows=()) -> InlineKeyboardMarkup | None:
    rows = link_rows(channel, download_url) + [list(r) for r in extra_rows]
    return markup(rows) if rows else None


def actions(post: dict, bot_username: str) -> InlineKeyboardMarkup:
    """Buttons under 'Post sent to channel!' and the shared-post screen."""
    t = post["token"]
    chat = post["channel_id"]
    return markup([
        [url_btn("📤 Share", telegram_share_url(share_link(bot_username, t)))],
        [btn("🔀 Resend post", "rs", "ra", t, 0)],
        [btn("🔁 Resend identical post", "rs", "ia", t, 0)],
        [btn("✈️ New post in channel", "npc", chat)],
        [btn("✏️ Edit post", "ed", t)],
        nav(f"ml:{chat}:a:0"),
    ])


def edit_panel(post: dict, channel: dict | None) -> InlineKeyboardMarkup:
    t = post["token"]
    label = LABELS.get(post.get("media_type"), "Media")
    link = message_link(channel, post.get("message_id")) if post.get("status") == "sent" else None
    share = url_btn("🔁 Share", telegram_share_url(link)) if link else btn("🔁 Share", "al", "ns")
    return markup([
        [btn(f"🖼 {label}", "em", t), btn("👀 See", "sv", t, "m")],
        [btn("🔤 Caption", "ec", t), btn("👀 See", "sv", t, "c")],
        [btn("⌨️ Buttons", "eb", t), btn("👀 See", "sv", t, "b")],
        [btn("🗑 Schedule deletion", "sd", t)],
        [btn("🔀 Resend post", "rs", "re", t, 0)],
        [share],
        nav(f"ml:{post['channel_id']}:a:0"),
    ])
