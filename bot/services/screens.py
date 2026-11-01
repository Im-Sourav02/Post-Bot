"""Texts for screens that are shown from several places."""
from bot import config
from bot.services.formatting import esc
from bot.services.links import message_link, share_link
from bot.services.timeutil import fmt

WELCOME = (
    "Hey {username}, 👋 Welcome to the <b>Infinix Syndicate Post Bot!</b>\n\n"
    "I'm a Post Bot built exclusively for Infinix Syndicate, designed to help you share your posts "
    "quickly and easily.\n\n"
    'Tap "New Post" below to get started and send your post.'
)

DATE_PROMPT = (
    "🕒 Send the date and time {what} in this format:\n"
    "<code>DD/MM/YYYY HH:MM</code>\n\n"
    "🌍 Timezone: <b>{tz}</b>\n"
    "🕰 Now: <code>{now}</code>"
)


def date_prompt(what: str, now: str) -> str:
    return DATE_PROMPT.format(what=what, tz=config.TIMEZONE, now=now)


def status_line(post: dict) -> str:
    status = post.get("status")
    if status == "sent":
        return f"✅ Sent on {fmt(post.get('sent_at'))}"
    if status == "scheduled":
        return f"🗓 Scheduled for {fmt(post.get('send_at'))}"
    if status == "deleted":
        return "🗑 Deleted"
    if status == "cancelled":
        return "❌ Cancelled" + (f" ({esc(post['last_error'])})" if post.get("last_error") else "")
    if status in ("sending", "deleting"):
        return "⏳ In progress..."
    return "📝 Draft"


def post_sent(post: dict, channel: dict | None, bot_username: str, header: str | None = None) -> str:
    title = esc(channel["title"]) if channel else "removed channel"
    if header is None:
        if post.get("status") == "scheduled":
            header = (f"🗓 <b>Post scheduled!</b>\n📢 {title} • {fmt(post.get('send_at'))} "
                      f"({esc(config.TIMEZONE)})")
        else:
            header = f"✅ <b>Post sent to channel!</b>\n📢 {title}"
    lines = [header]
    if post.get("delete_at"):
        lines.append(f"🗑 Will be deleted on {fmt(post['delete_at'])}")
    elif post.get("delete_delay"):
        lines.append(f"🗑 Will be deleted {_duration(post['delete_delay'])} after sending")
    link = share_link(bot_username, post["token"]).removeprefix("https://")
    lines.append(
        "\n• Press 'Resend post' to send this post to other channels\n"
        "• Press 'Resend identical post' to send it to other channels with the same settings "
        "(sending schedule and/or deletion schedule)\n"
        f"• Through this link you can make other users use this post: {link}"
    )
    return "\n".join(lines)


def edit_panel(post: dict, channel: dict | None, bot_username: str) -> str:
    link = message_link(channel, post.get("message_id")) if post.get("status") == "sent" else None
    lines = [
        "📩 <b>Select what you want to edit</b>\n",
        f"📢 Channel: {esc(channel['title']) if channel else 'removed channel'}",
        f"📌 Status: {status_line(post)}",
    ]
    if post.get("delete_at") and post.get("status") in ("sent", "scheduled"):
        lines.append(f"🗑 Deletion: {fmt(post['delete_at'])}")
    lines += [
        "",
        f"<b>Share link:</b> {share_link(bot_username, post['token']).removeprefix('https://')}",
        f"<b>Message link:</b> {link or '— (not sent yet)'}",
    ]
    return "\n".join(lines)


def _duration(seconds: int) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = [f"{days}d" if days else "", f"{hours}h" if hours else "", f"{minutes}m" if minutes else ""]
    return " ".join(p for p in parts if p) or f"{seconds}s"
