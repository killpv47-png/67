"""Bridge: reply-keyboard taps and slash commands reuse the inline-callback handlers.

Instead of duplicating every flow for Message vs CallbackQuery, we keep a small
registry of entry points keyed by callback data and call them with the Message.
Each handler module registers its entry points with ``entry(data)``.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ..app import AppContext

Entry = Callable[[Message, AppContext, str, FSMContext], Awaitable[None]]
_ENTRIES: dict[str, Entry] = {}


def entry(data: str):
    def deco(fn: Entry) -> Entry:
        _ENTRIES[data] = fn
        return fn
    return deco


async def dispatch_callback(msg: Message, data: str, app: AppContext, lang: str, state: FSMContext) -> None:
    fn = _ENTRIES.get(data)
    if fn:
        await fn(msg, app, lang, state)
