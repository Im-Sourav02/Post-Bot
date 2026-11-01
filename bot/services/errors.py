"""Turn Telegram API errors into short, friendly messages for admins."""
from pyrogram.errors import FloodWait, RPCError

NO_ACCESS = {
    "CHANNEL_PRIVATE", "CHANNEL_INVALID", "CHAT_WRITE_FORBIDDEN", "PEER_ID_INVALID",
    "USER_NOT_PARTICIPANT", "CHAT_FORBIDDEN", "CHAT_ID_INVALID", "USER_BANNED_IN_CHANNEL",
}
NO_RIGHTS = {
    "CHAT_ADMIN_REQUIRED", "MESSAGE_DELETE_FORBIDDEN", "MESSAGE_AUTHOR_REQUIRED",
    "CHAT_SEND_MEDIA_FORBIDDEN", "CHAT_SEND_PHOTOS_FORBIDDEN", "CHAT_SEND_VIDEOS_FORBIDDEN",
    "CHAT_SEND_DOCS_FORBIDDEN", "CHAT_SEND_AUDIOS_FORBIDDEN", "CHAT_SEND_VOICES_FORBIDDEN",
    "CHAT_SEND_GIFS_FORBIDDEN",
}
MESSAGE_GONE = {"MESSAGE_ID_INVALID", "MESSAGE_EMPTY"}
BAD_MEDIA = {"MEDIA_EMPTY", "MEDIA_INVALID", "FILE_REFERENCE_EXPIRED", "FILE_ID_INVALID", "WEBPAGE_MEDIA_EMPTY"}


def error_id(e: BaseException) -> str:
    return getattr(e, "ID", None) or ""


def is_message_gone(e: BaseException) -> bool:
    return error_id(e) in MESSAGE_GONE


def is_not_modified(e: BaseException) -> bool:
    return error_id(e) == "MESSAGE_NOT_MODIFIED"


def friendly(e: BaseException) -> str:
    if isinstance(e, FloodWait):
        return f"⏳ Telegram is rate-limiting the bot. Please try again in {e.value} seconds."
    eid = error_id(e)
    if eid in NO_ACCESS:
        return ("🚫 I can't access that channel anymore. "
                "Make sure the bot is still a member and an admin of the channel.")
    if eid in NO_RIGHTS:
        return ("🚫 I'm missing admin rights in that channel. "
                "Give the bot permission to post, edit and delete messages.")
    if eid in MESSAGE_GONE:
        return "🗑 That message no longer exists in the channel (it was probably deleted)."
    if eid == "MESSAGE_EDIT_TIME_EXPIRED":
        return "⌛ Telegram no longer allows editing this message."
    if eid == "MEDIA_CAPTION_TOO_LONG":
        return "⚠️ The caption is too long for Telegram (max 1024 characters)."
    if eid in ("BUTTON_URL_INVALID", "BUTTON_TYPE_INVALID"):
        return "🔗 One of the button links was rejected by Telegram. Check the Download/Premium/Backup links."
    if eid in BAD_MEDIA:
        return "🖼 Telegram couldn't use this media file. Please send the media again."
    if eid == "MESSAGE_NOT_MODIFIED":
        return "ℹ️ Nothing changed."
    if isinstance(e, RPCError):
        return f"⚠️ Telegram error: {eid or type(e).__name__}"
    return "⚠️ Something went wrong while talking to Telegram. Please try again."
