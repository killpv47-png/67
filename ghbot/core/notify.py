"""Notification bus.

The user explicitly wants a notification for every step of every job.  All code
paths (GitHub ops, uploads, AI tool calls, lifecycle) go through ``Notifier`` so
that: (a) every message is redacted, (b) stored in the DB for the "recent
notifications" view, (c) rate-limited against Telegram's 429s, and (d) a single
"progress message" can be edited in place instead of spamming the chat.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from .db import Database
from .redact import redact

log = logging.getLogger(__name__)

TG_LIMIT = 4096


def chunk(text: str, size: int = TG_LIMIT - 64) -> list[str]:
    if len(text) <= size:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > size:
            if cur:
                out.append(cur)
            while len(line) > size:
                out.append(line[:size])
                line = line[size:]
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


class Notifier:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self._last_edit: dict[tuple[int, int], float] = {}

    async def _send_raw(self, chat_id: int, text: str, markup: InlineKeyboardMarkup | None = None, html: bool = True):
        for attempt in range(5):
            try:
                return await self.bot.send_message(
                    chat_id, text, reply_markup=markup, parse_mode="HTML" if html else None,
                    disable_web_page_preview=True,
                )
            except TelegramRetryAfter as e:
                await asyncio.sleep(min(e.retry_after, 60) + 0.5)
            except TelegramForbiddenError as e:  # user blocked the bot / deleted account
                log.warning("send forbidden for %s: %s", chat_id, e)
                return None
            except TelegramNetworkError as e:
                log.warning("telegram network error (attempt %d): %s", attempt + 1, e)
                await asyncio.sleep(1.5 * (attempt + 1))
            except TelegramBadRequest as e:
                low = str(e).lower()
                if html and ("parse entities" in low or "can't parse" in low):
                    html = False  # fall back to plain text if our HTML is malformed
                    continue
                if "message is too long" in low:
                    text = text[: TG_LIMIT - 64]
                    continue
                log.warning("send failed: %s", e)
                return None
            except Exception as e:  # never let a notification kill a flow
                log.warning("send failed unexpectedly: %s", e)
                return None
        return None

    async def send(self, chat_id: int, text: str, *, kind: str = "info", markup: InlineKeyboardMarkup | None = None,
                   html: bool = True, store: bool = True):
        text = redact(text)
        if store:
            try:
                await self.db.add_notification(chat_id, kind, text)
            except Exception:  # pragma: no cover
                log.exception("notification store failed")
        msg = None
        parts = chunk(text)
        for i, part in enumerate(parts):
            msg = await self._send_raw(chat_id, part, markup if i == len(parts) - 1 else None, html)
        return msg

    async def step(self, chat_id: int, text: str, *, job_id: str | None = None, ok: bool = True):
        """One progress step: stored on the job + sent as a notification."""
        icon = "✅" if ok else "❌"
        if job_id:
            try:
                await self.db.job_step(job_id, text, ok)
            except Exception:  # pragma: no cover
                log.exception("job step store failed")
        return await self.send(chat_id, f"{icon} {text}", kind="step")

    async def edit(self, chat_id: int, message_id: int, text: str, markup: InlineKeyboardMarkup | None = None,
                   min_interval: float = 1.2) -> bool:
        """Edit a progress message in place, throttled to avoid 429s."""
        key = (chat_id, message_id)
        now = time.time()
        if now - self._last_edit.get(key, 0) < min_interval:
            return False
        self._last_edit[key] = now
        text = redact(text)[: TG_LIMIT - 16]
        try:
            await self.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup,
                                             parse_mode="HTML", disable_web_page_preview=True)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(min(e.retry_after, 60) + 0.5)
            return False
        except TelegramBadRequest as e:
            if "not modified" in str(e):
                return True
            if "parse entities" in str(e).lower() or "can't parse" in str(e).lower():
                try:
                    await self.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
                    return True
                except Exception:
                    return False
            return False
        except Exception as e:
            log.warning("edit failed: %s", e)
            return False

    async def broadcast(self, user_ids: list[int], text: str, kind: str = "system"):
        for uid in user_ids:
            await self.send(uid, text, kind=kind)
