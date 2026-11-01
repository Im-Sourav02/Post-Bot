"""Dispatch callback queries by prefix and user input by conversation step."""
import logging
import time
from typing import Awaitable, Callable

from pyrogram import Client
from pyrogram.errors import RPCError
from pyrogram.types import CallbackQuery, Message

from bot.db import states
from bot.keyboards import main_menu
from bot.services import ui
from bot.services.errors import friendly
from bot.services.formatting import html_to_plain
from bot.services.poster import PostError

log = logging.getLogger(__name__)

CallbackFn = Callable[[Client, CallbackQuery, list[str]], Awaitable[object]]
StepFn = Callable[[Client, Message, dict], Awaitable[None]]

CALLBACKS: dict[str, CallbackFn] = {}
STEPS: dict[str, StepFn] = {}

# Callbacks that must not reset the user's pending input step.
KEEP_STATE = {"noop", "al"}

ALERTS = {
    "ns": "This post hasn't been sent to the channel yet, so there is no message link to share.",
}

_seen_albums: dict[str, float] = {}


def callback(prefix: str):
    def deco(fn: CallbackFn) -> CallbackFn:
        CALLBACKS[prefix] = fn
        return fn
    return deco


def step(name: str):
    def deco(fn: StepFn) -> StepFn:
        STEPS[name] = fn
        return fn
    return deco


@callback("noop")
async def _noop(client: Client, cq: CallbackQuery, args: list[str]):
    return None


@callback("al")
async def _alert(client: Client, cq: CallbackQuery, args: list[str]):
    return ALERTS.get(args[0] if args else "", "ℹ️"), True


async def on_callback(client: Client, cq: CallbackQuery) -> None:
    parts = (cq.data or "").split(":")
    fn = CALLBACKS.get(parts[0])
    if fn is None or cq.message is None:
        await _answer(cq, ("This button is no longer valid. Use /start.", True))
        return
    if parts[0] not in KEEP_STATE:
        await states.clear(cq.from_user.id)
    try:
        result = await fn(client, cq, parts[1:])
    except PostError as e:
        result = (html_to_plain(e.text), True)
    except (ValueError, IndexError):
        result = ("This button is no longer valid. Use /start.", True)
    except RPCError as e:
        log.warning("Callback %s failed: %s", parts[0], getattr(e, "ID", e))
        result = (friendly(e), True)
    except Exception:
        log.exception("Callback %s crashed", parts[0])
        result = ("⚠️ Something went wrong. Please try again.", True)
    await _answer(cq, result)


async def _answer(cq: CallbackQuery, result) -> None:
    text, alert = (result if isinstance(result, tuple) else (result, False))
    try:
        await cq.answer(text[:200] if text else None, show_alert=alert)
    except RPCError:
        pass


def first_of_album(group_id: str | None) -> bool:
    """Albums arrive as several messages; only react to the first one."""
    if not group_id:
        return True
    now = time.monotonic()
    for key, seen in list(_seen_albums.items()):
        if now - seen > 120:
            del _seen_albums[key]
    if group_id in _seen_albums:
        return False
    _seen_albums[group_id] = now
    return True


async def on_message(client: Client, msg: Message) -> None:
    if not first_of_album(msg.media_group_id):
        return
    if msg.text and msg.text.startswith("/"):
        await msg.reply("❓ Unknown command. Send /help to see what I can do.")
        return
    state = await states.get(msg.from_user.id)
    handler = STEPS.get(state["step"]) if state else None
    if handler is None:
        hint = "Tap ✈️ New Post first, then send your media." if msg.media else "Use the buttons below 👇"
        await ui.respond(client, msg.chat.id, hint, main_menu())
        return
    try:
        await handler(client, msg, state)
    except PostError as e:
        await msg.reply(e.text)
    except RPCError as e:
        log.warning("Step %s failed: %s", state["step"], getattr(e, "ID", e))
        await msg.reply(friendly(e))
    except Exception:
        log.exception("Step %s crashed", state["step"])
        await msg.reply("⚠️ Something went wrong. Please try again.")
