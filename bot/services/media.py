from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InputMediaAnimation,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

SUPPORTED = ("photo", "video", "animation", "document", "audio", "voice")
LABELS = {
    "photo": "Photo",
    "video": "Video",
    "animation": "GIF",
    "document": "File",
    "audio": "Audio",
    "voice": "Voice",
}

ALBUM_TEXT = (
    "📚 <b>Albums can't be used for this post format.</b>\n"
    "Telegram doesn't allow inline buttons on albums, so the Premium/Backup/Download buttons "
    "couldn't be attached. Please send a <b>single</b> photo, video, GIF, file, audio or voice message."
)
STICKER_TEXT = (
    "🎭 <b>Stickers can't be used for this post format.</b>\n"
    "Telegram doesn't allow captions on stickers, so the caption couldn't be attached. "
    "Please send a photo, video, GIF, file, audio or voice message instead."
)
ROUND_TEXT = (
    "⏺ <b>Round videos can't be used for this post format.</b>\n"
    "Telegram doesn't allow captions on round video messages, so the caption couldn't be attached. "
    "Please send it as a normal video instead."
)
NEED_MEDIA_TEXT = (
    "🖼 <b>This post format needs a media.</b>\n"
    "Please send a photo, video, GIF, file, audio or voice message (you can include the caption with it)."
)
OTHER_TEXT = (
    "⚠️ This type of message isn't supported.\n"
    "Please send a photo, video, GIF, file, audio or voice message."
)


class UnsupportedMedia(Exception):
    def __init__(self, text: str):
        super().__init__(text)
        self.text = text


def extract(msg: Message) -> tuple[str, str]:
    """Return (media_type, file_id) or raise UnsupportedMedia with a user-facing explanation."""
    if msg.media_group_id:
        raise UnsupportedMedia(ALBUM_TEXT)
    if msg.sticker:
        raise UnsupportedMedia(STICKER_TEXT)
    if msg.video_note:
        raise UnsupportedMedia(ROUND_TEXT)
    for kind in SUPPORTED:
        obj = getattr(msg, kind, None)
        if obj is not None:
            return kind, obj.file_id
    if msg.text:
        raise UnsupportedMedia(NEED_MEDIA_TEXT)
    raise UnsupportedMedia(OTHER_TEXT)


async def send(
    client: Client,
    chat_id: int,
    media_type: str,
    file_id: str,
    caption: str,
    reply_markup=None,
    protect_content: bool = False,
) -> Message:
    methods = {
        "photo": client.send_photo,
        "video": client.send_video,
        "animation": client.send_animation,
        "document": client.send_document,
        "audio": client.send_audio,
        "voice": client.send_voice,
    }
    return await methods[media_type](
        chat_id,
        file_id,
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
        protect_content=protect_content,
    )


def input_media(media_type: str, file_id: str, caption: str):
    """InputMedia for editMessageMedia. Voice messages can't be used there, so None is returned for them."""
    cls = {
        "photo": InputMediaPhoto,
        "video": InputMediaVideo,
        "animation": InputMediaAnimation,
        "document": InputMediaDocument,
        "audio": InputMediaAudio,
    }.get(media_type)
    if cls is None:
        return None
    return cls(file_id, caption=caption, parse_mode=ParseMode.HTML)
