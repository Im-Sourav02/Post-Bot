import asyncio
import logging
from urllib.parse import urlparse

from pyrogram import Client, idle
from pyrogram.enums import ParseMode
from pyrogram.errors import RPCError

from bot import config, db
from bot.db import channels
from bot.handlers import register
from bot.services import scheduler

log = logging.getLogger("bot")


class RedactingFormatter(logging.Formatter):
    """Make sure secrets never reach the logs, even inside tracebacks."""

    def __init__(self, fmt: str, secrets: list[str]):
        super().__init__(fmt)
        self._secrets = [s for s in secrets if s and len(s) >= 6]

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text


def setup_logging() -> None:
    secrets = [config.BOT_TOKEN, config.API_HASH, config.BOT_TOKEN.split(":")[-1]]
    try:
        secrets.append(urlparse(config.MONGO_URI).password or "")
    except ValueError:
        pass
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s", secrets))
    logging.basicConfig(level=config.LOG_LEVEL, handlers=[handler])
    logging.getLogger("pyrogram").setLevel(logging.WARNING)


async def refresh_channels(app: Client) -> None:
    """Re-resolve stored channels after a restart (the session is in-memory) and refresh their titles."""
    for channel in await channels.list_all():
        try:
            chat = await app.get_chat(channel["tg_chat_id"])
            await channels.set_fields(channel["tg_chat_id"], title=chat.title or channel["title"],
                                      username=chat.username)
        except (RPCError, KeyError, ValueError) as e:
            log.warning("Channel %s (%s) is not reachable: %s", channel["title"], channel["tg_chat_id"],
                        getattr(e, "ID", type(e).__name__))


async def background(app: Client) -> None:
    await refresh_channels(app)
    await scheduler.run(app)


async def main() -> None:
    setup_logging()
    await db.connect()
    app = Client(
        "infinix_postbot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
        in_memory=True,
        parse_mode=ParseMode.HTML,
        sleep_threshold=30,
    )
    register(app)
    await app.start()
    log.info("Bot started as @%s (timezone %s)", app.me.username, config.TIMEZONE)
    task = asyncio.create_task(background(app))
    try:
        await idle()
    finally:
        task.cancel()
        await app.stop()
        db.close()
        log.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
