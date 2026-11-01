import html
import re
from urllib.parse import urlparse

from pyrogram import raw
from pyrogram.enums import MessageEntityType as ET
from pyrogram.parser import utils
from pyrogram.parser.html import HTML
from pyrogram.types import Message, MessageEntity

from bot import config

esc = html.escape

_SIMPLE_TAGS = {
    ET.BOLD: "b",
    ET.ITALIC: "i",
    ET.UNDERLINE: "u",
    ET.STRIKETHROUGH: "s",
    ET.CODE: "code",
    ET.SPOILER: "spoiler",
}


def _tags(entity: MessageEntity) -> tuple[str, str] | None:
    t = entity.type
    if t in _SIMPLE_TAGS:
        name = _SIMPLE_TAGS[t]
        return f"<{name}>", f"</{name}>"
    if t == ET.PRE:
        lang = getattr(entity, "language", None)
        return (f'<pre language="{esc(lang)}">' if lang else "<pre>"), "</pre>"
    if t == ET.BLOCKQUOTE:
        return ("<blockquote expandable>" if getattr(entity, "expandable", False) else "<blockquote>"), "</blockquote>"
    if t == ET.TEXT_LINK and entity.url:
        return f'<a href="{esc(entity.url)}">', "</a>"
    if t == ET.TEXT_MENTION and entity.user:
        return f'<a href="tg://user?id={entity.user.id}">', "</a>"
    if t == ET.CUSTOM_EMOJI and entity.custom_emoji_id:
        return f'<tg-emoji emoji-id="{entity.custom_emoji_id}">', "</tg-emoji>"
    return None


_RAW_SIMPLE_TAGS = {
    raw.types.MessageEntityBold: "b",
    raw.types.MessageEntityItalic: "i",
    raw.types.MessageEntityUnderline: "u",
    raw.types.MessageEntityStrike: "s",
    raw.types.MessageEntityCode: "code",
    raw.types.MessageEntitySpoiler: "spoiler",
}

_HTML_TAG_RE = re.compile(
    r"</?(?:b|strong|i|em|u|ins|s|strike|del|a|code|pre|blockquote|spoiler|tg-spoiler|tg-emoji)\b[^>]*>",
    re.IGNORECASE,
)

Span = tuple[int, int, str, str]


def _raw_tags(entity: raw.base.MessageEntity) -> tuple[str, str] | None:
    if type(entity) in _RAW_SIMPLE_TAGS:
        name = _RAW_SIMPLE_TAGS[type(entity)]
        return f"<{name}>", f"</{name}>"
    if isinstance(entity, raw.types.MessageEntityPre):
        return (f'<pre language="{esc(entity.language)}">' if entity.language else "<pre>"), "</pre>"
    if isinstance(entity, raw.types.MessageEntityBlockquote):
        return ("<blockquote expandable>" if entity.collapsed else "<blockquote>"), "</blockquote>"
    if isinstance(entity, raw.types.MessageEntityTextUrl):
        url = normalize_url(entity.url)
        return (f'<a href="{esc(url)}">', "</a>") if url else None
    if isinstance(entity, raw.types.InputMessageEntityMentionName) and isinstance(entity.user_id, int):
        return f'<a href="tg://user?id={entity.user_id}">', "</a>"
    if isinstance(entity, raw.types.MessageEntityCustomEmoji):
        return f'<tg-emoji emoji-id="{entity.document_id}">', "</tg-emoji>"
    return None


def _render(text: str, spans: list[Span], escape: bool = True) -> str:
    src = utils.add_surrogates(text)
    opens: dict[int, list[str]] = {}
    closes: dict[int, list[str]] = {}
    for offset, length, open_tag, close_tag in sorted(spans, key=lambda s: (s[0], -s[1])):
        if length <= 0:
            continue
        opens.setdefault(offset, []).append(open_tag)
        closes.setdefault(offset + length, []).insert(0, close_tag)
    out: list[str] = []
    for i in range(len(src) + 1):
        out.extend(closes.get(i, ()))
        out.extend(opens.get(i, ()))
        if i < len(src):
            out.append(esc(src[i], quote=False) if escape else src[i])
    return utils.remove_surrogates("".join(out))


def _entity_spans(entities: list[MessageEntity] | None) -> list[Span]:
    return [(e.offset, e.length, *tags) for e in entities or [] if (tags := _tags(e))]


def entities_to_html(text: str | None, entities: list[MessageEntity] | None) -> str:
    """Convert Telegram text + entities to HTML, escaping all plain text (Kurigram's .html doesn't)."""
    if not text:
        return ""
    return _render(text, _entity_spans(entities))


def message_html(msg: Message) -> str:
    """HTML of a message's caption (media) or text, preserving formatting."""
    if msg.caption:
        return entities_to_html(msg.caption, msg.caption_entities)
    if msg.text:
        return entities_to_html(msg.text, msg.entities)
    return ""


async def html_message_html(msg: Message) -> str | None:
    """Like message_html, but HTML tags typed in the text are applied too. None if they can't be parsed."""
    text = msg.text or msg.caption
    entities = msg.entities if msg.text else msg.caption_entities
    if not text or not _HTML_TAG_RE.search(text):
        return message_html(msg)
    try:
        parsed = await HTML(None).parse(_render(text, _entity_spans(entities), escape=False))
    except (ValueError, TypeError):
        return None
    spans = [(e.offset, e.length, *tags) for e in parsed["entities"] or [] if (tags := _raw_tags(e))]
    return _render(parsed["message"], spans)


def html_to_plain(value: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or ""))


def tg_len(value_html: str | None) -> int:
    """Visible length as Telegram counts it (UTF-16 code units after entity parsing)."""
    return len(html_to_plain(value_html).encode("utf-16-le")) // 2


def compose_caption(caption_html: str | None, signature_html: str | None) -> str:
    caption_html = (caption_html or "").strip()
    signature_html = (signature_html or "").strip()
    if caption_html and signature_html:
        return f"{caption_html}\n\n{signature_html}"
    return caption_html or signature_html


def caption_overflow(caption_html: str | None, signature_html: str | None) -> int:
    """How many characters must be cut for caption + signature to fit Telegram's limit (0 if it fits)."""
    return max(0, tg_len(compose_caption(caption_html, signature_html)) - config.CAPTION_LIMIT)


def too_long_text(caption_html: str | None, signature_html: str | None) -> str:
    total = tg_len(compose_caption(caption_html, signature_html))
    over = total - config.CAPTION_LIMIT
    return (
        f"⚠️ The caption is too long: <b>{total}/{config.CAPTION_LIMIT}</b> characters "
        f"(including the channel signature).\nPlease cut <b>{over}</b> characters and send it again."
    )


def normalize_url(text: str | None) -> str | None:
    """Return a valid http(s)/tg URL or None. Bare 't.me/...' style links get https:// added."""
    value = (text or "").strip()
    if not value or any(c.isspace() for c in value):
        return None
    if value.lower().startswith("tg://"):
        return value if len(value) > 5 else None
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        value = "https://" + value
    try:
        parsed = urlparse(value)
        host = parsed.hostname or ""
    except ValueError:
        return None
    if parsed.scheme.lower() not in ("http", "https") or "." not in host:
        return None
    return value


def snippet(caption_html: str | None, words: int = 6, max_chars: int = 40) -> str:
    plain = " ".join(html_to_plain(caption_html).split())
    if not plain:
        return "(no caption)"
    cut = " ".join(plain.split(" ")[:words])
    if len(cut) > max_chars:
        cut = cut[:max_chars].rstrip()
    return cut + "..." if cut != plain else cut
