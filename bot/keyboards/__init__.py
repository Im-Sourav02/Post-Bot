from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import config

NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def cb(*parts) -> str:
    data = ":".join(str(p) for p in parts)
    if len(data.encode()) > 64:
        raise ValueError(f"callback_data too long ({len(data.encode())} bytes): {data}")
    return data


def btn(text: str, *parts) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=cb(*parts))


def url_btn(text: str, link: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, url=link)


def markup(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(r) for r in rows if r])


def nav(back: str) -> list[InlineKeyboardButton]:
    return [btn("🏠 Menu", "menu"), btn("🔙 Back", back)]


def main_menu() -> InlineKeyboardMarkup:
    return markup([
        [btn("📂 My Posts", "mp", 0), btn("✈️ New Post", "np", 0)],
        [btn("⚙️ Settings", "st", 0)],
    ])


def only_nav(back: str) -> InlineKeyboardMarkup:
    return markup([nav(back)])


def _short(title: str, limit: int = 28) -> str:
    title = title or "Untitled"
    return title if len(title) <= limit else title[: limit - 1] + "…"


def channel_grid(
    channels: list[dict],
    page: int,
    select_prefix: str,
    page_prefix: str,
    back: str,
) -> InlineKeyboardMarkup:
    """2-column channel picker: buttons '📢 {title}', paginated, plus Menu/Back."""
    per_page = config.CHANNELS_PER_PAGE
    pages = max(1, -(-len(channels) // per_page))
    page = min(max(page, 0), pages - 1)
    chunk = channels[page * per_page:(page + 1) * per_page]
    rows = []
    for i in range(0, len(chunk), 2):
        rows.append([
            btn(f"📢 {_short(ch['title'])}", select_prefix, ch["tg_chat_id"]) for ch in chunk[i:i + 2]
        ])
    if pages > 1:
        rows.append([
            btn("⬅️", page_prefix, page - 1) if page > 0 else btn("🚫", "noop"),
            btn(f"{page + 1}/{pages}", "noop"),
            btn("➡️", page_prefix, page + 1) if page < pages - 1 else btn("🚫", "noop"),
        ])
    rows.append(nav(back))
    return markup(rows)
