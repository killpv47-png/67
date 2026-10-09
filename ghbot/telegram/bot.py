"""Dispatcher assembly."""

from __future__ import annotations

import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from ..core.config import Settings
from ..core.db import Database
from ..core.notify import Notifier
from .app import AppContext
from .handlers import ROUTERS
from .middleware import AccessMiddleware

COMMANDS = [
    ("start", "Start / menu"), ("menu", "Main menu"), ("ai", "Ask GITHUB_AI"), ("repos", "Repositories"),
    ("newrepo", "Create repository"), ("upload", "Upload ZIP to a repo"), ("secrets", "Manage secrets"),
    ("actions", "GitHub Actions"), ("scan", "Rescan account"), ("notifications", "Notifications & jobs"),
    ("ai_new", "New AI session"), ("ai_stop", "Stop AI"), ("settings", "Settings"), ("lang", "Language"),
    ("token", "Set GitHub token"), ("restart", "Restart bot (new run)"), ("help", "Documentation"), ("cancel", "Cancel"),
]


def build(settings: Settings, db: Database) -> tuple[Bot, Dispatcher, AppContext]:
    # TELEGRAM_API_URL lets you point at a local Bot API server (or the test fake); default = api.telegram.org
    session = None
    api_url = os.environ.get("TELEGRAM_API_URL", "").rstrip("/")
    if api_url:
        session = AiohttpSession(api=TelegramAPIServer.from_base(api_url))
    bot = Bot(settings.bot_token, session=session,
              default=DefaultBotProperties(parse_mode="HTML", link_preview_is_disabled=True))
    dp = Dispatcher(storage=MemoryStorage())
    app = AppContext(settings=settings, db=db, bot=bot, notifier=Notifier(bot, db))
    mw = AccessMiddleware(app)
    dp.message.middleware(mw)
    dp.callback_query.middleware(mw)
    for r in ROUTERS:
        # routers are module singletons; detach if a previous Dispatcher (tests, restart) owns them
        if r.parent_router is not None:
            r._parent_router = None
        dp.include_router(r)
    return bot, dp, app


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in COMMANDS])
