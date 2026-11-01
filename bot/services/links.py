from urllib.parse import quote


def share_link(bot_username: str, token: str) -> str:
    return f"https://t.me/{bot_username}?start=resend{token}"


def message_link(channel: dict | None, message_id: int | None) -> str | None:
    if not channel or not message_id:
        return None
    if channel.get("username"):
        return f"https://t.me/{channel['username']}/{message_id}"
    internal_id = str(channel["tg_chat_id"]).removeprefix("-100")
    return f"https://t.me/c/{internal_id}/{message_id}"


def telegram_share_url(link: str) -> str:
    return f"https://t.me/share/url?url={quote(link, safe='')}"
