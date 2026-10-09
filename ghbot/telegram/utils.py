from __future__ import annotations

import html
import time
from datetime import datetime, timezone

from aiogram.types import CallbackQuery, Message


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=False)


def age(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    secs = (datetime.now(timezone.utc) - dt).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{int(secs // size)}{unit} ago"
    return "just now"


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def hhmm(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


async def edit_or_send(event: Message | CallbackQuery, text: str, markup=None) -> Message | None:
    """Edit the callback's message if possible, otherwise send a new one."""
    if isinstance(event, CallbackQuery) and event.message:
        try:
            return await event.message.edit_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            try:
                return await event.message.answer(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
            except Exception:
                return await event.message.answer(text, reply_markup=markup)
    msg = event if isinstance(event, Message) else event.message
    try:
        return await msg.answer(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        return await msg.answer(text, reply_markup=markup)


async def safe_delete(msg: Message) -> None:
    try:
        await msg.delete()
    except Exception:
        pass
