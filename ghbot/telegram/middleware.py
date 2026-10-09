"""Access control + per-user language + fast ack middleware."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from ..i18n import t
from .app import AppContext

log = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    """Owner lock: if OWNER_IDS is set, only those ids pass. Otherwise the first
    user to /start becomes owner and the bot locks to them (stored in kv)."""

    def __init__(self, app: AppContext):
        self.app = app

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        tg_id = user.id
        allowed = True
        if self.app.settings.owner_ids:
            allowed = tg_id in self.app.settings.owner_ids
        else:
            owners = await self.app.db.kv_get("owners", [])
            if owners:
                allowed = tg_id in owners
            else:
                await self.app.db.kv_set("owners", [tg_id])
                log.info("first user %s became owner", tg_id)
        if not allowed:
            text = t("en", "not_owner", id=tg_id)
            if isinstance(event, Message):
                await event.answer(text, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔", show_alert=True)
            return None
        row = await self.app.db.upsert_user(tg_id, user.username)
        data["app"] = self.app
        data["lang"] = row["lang"] or "en"
        data["user_row"] = row
        # fast ack: callback spinners stop immediately
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
        return await handler(event, data)
