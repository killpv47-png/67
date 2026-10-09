"""Shared application context injected into every handler via aiogram's workflow data."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from aiogram import Bot

from ..core.config import Settings
from ..core.crypto import decrypt_str, encrypt_str
from ..core.db import Database
from ..core.notify import Notifier
from ..core.redact import register_secret
from ..github.client import GitHubClient
from ..i18n import t as _t

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    settings: Settings
    db: Database
    bot: Bot
    notifier: Notifier
    lifecycle: Optional[object] = None  # LifecycleManager (set after construction)
    agents: dict[int, object] = field(default_factory=dict)   # tg_id -> Agent
    ai_tasks: dict[int, asyncio.Task] = field(default_factory=dict)
    repo_cache: dict[int, list[dict]] = field(default_factory=dict)

    # ------------------------------------------------------------ helpers
    async def lang(self, tg_id: int) -> str:
        u = await self.db.get_user(tg_id)
        return (u["lang"] if u else None) or "en"

    async def t(self, tg_id: int, key: str, **kw) -> str:
        return _t(await self.lang(tg_id), key, **kw)

    def is_allowed(self, tg_id: int, user_count: int) -> bool:
        if self.settings.owner_ids:
            return tg_id in self.settings.owner_ids
        return True  # first-come: handled in onboarding (first user becomes owner)

    async def token_for(self, tg_id: int) -> str | None:
        u = await self.db.get_user(tg_id)
        if not u or not u["gh_token_enc"]:
            return None
        try:
            tok = decrypt_str(u["gh_token_enc"], self.settings.state_key)
        except Exception:
            log.error("cannot decrypt token for %s (STATE_KEY changed?)", tg_id)
            return None
        register_secret(tok)
        return tok

    async def save_token(self, tg_id: int, token: str) -> None:
        register_secret(token)
        await self.db.set_user_fields(tg_id, gh_token_enc=encrypt_str(token, self.settings.state_key))

    async def gh(self, tg_id: int) -> GitHubClient | None:
        tok = await self.token_for(tg_id)
        if not tok:
            return None

        async def on_wait(secs: float, kind: str):
            await self.notifier.send(tg_id, await self.t(tg_id, "gh_wait", secs=int(secs)), kind="wait", store=False)

        return GitHubClient(tok, on_wait=on_wait)

    async def repos(self, tg_id: int, refresh: bool = False) -> list[dict]:
        if not refresh and tg_id in self.repo_cache:
            return self.repo_cache[tg_id]
        gh = await self.gh(tg_id)
        if not gh:
            return []
        try:
            repos = await gh.list_repos(max_pages=5)
        finally:
            await gh.aclose()
        self.repo_cache[tg_id] = repos
        from .keyboards import persist_repo_ids, register_repos
        register_repos(repos)
        await persist_repo_ids(self.db)
        return repos

    # ---------------------------------------------------------------- AI cfg
    async def ai_config(self, tg_id: int) -> dict | None:
        cfg = await self.db.kv_get(f"ai:{tg_id}")
        if not cfg or not cfg.get("model"):
            return None
        try:
            cfg["api_key"] = decrypt_str(bytes.fromhex(cfg["api_key_enc"]), self.settings.state_key)
        except Exception:
            return None
        register_secret(cfg["api_key"])
        return cfg

    async def save_ai_config(self, tg_id: int, base_url: str, api_key: str, model: str | None) -> None:
        register_secret(api_key)
        await self.db.kv_set(f"ai:{tg_id}", {
            "base_url": base_url, "api_key_enc": encrypt_str(api_key, self.settings.state_key).hex(), "model": model,
        })

    @property
    def workspace(self) -> Path:
        return self.settings.workspace_dir
