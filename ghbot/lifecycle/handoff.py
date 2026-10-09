"""Run lifecycle inside GitHub Actions.

A job dies at 6h.  ``LifecycleManager``:
  * checkpoints the DB every ``checkpoint_interval_s`` (only when changed)
  * at ``max_run_minutes`` (or on demand) performs a HANDOFF:
      1. tell every user  2. final checkpoint  3. dispatch the same workflow
      again via GH_PAT  4. stop polling and exit 0 (the workflow ``concurrency``
      group makes the new run wait, so there is never a double-poll)
  * runs the "watch" poller that notifies users about workflow runs they follow.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from ..core.config import Settings
from ..core.db import Database
from ..core.notify import Notifier
from ..github.client import GitHubClient, GitHubError
from ..i18n import t
from .checkpoint import Checkpointer

log = logging.getLogger(__name__)

RUN_ICON = {"success": "✅", "failure": "❌", "cancelled": "⏹", "in_progress": "🏃", "queued": "⏳",
            "skipped": "⏭", "timed_out": "⏰", "completed": "🏁", "waiting": "⏳", "requested": "⏳"}


class LifecycleManager:
    def __init__(self, settings: Settings, db: Database, notifier: Notifier, checkpointer: Checkpointer,
                 *, stop: Callable[[], Awaitable[None]], gh_factory: Callable[[int], Awaitable[GitHubClient | None]]):
        self.s = settings
        self.db = db
        self.notifier = notifier
        self.cp = checkpointer
        self.stop = stop
        self.gh_factory = gh_factory
        self.started = time.time()
        self.handing_off = False
        self._tasks: list[asyncio.Task] = []

    async def start(self, restored: str):
        for u in await self.db.all_users():
            await self.notifier.send(
                u["tg_id"],
                t(u["lang"], "lifecycle_hello", run=self.s.run_id or "local", attempt=self.s.run_attempt,
                  restored=restored, minutes=self.s.max_run_minutes), kind="system")
            if not self.cp.enabled and self.s.in_actions:
                await self.notifier.send(u["tg_id"], t(u["lang"], "lifecycle_no_pat"), kind="system")
        self._tasks.append(asyncio.create_task(self._checkpoint_loop(), name="checkpoint"))
        self._tasks.append(asyncio.create_task(self._budget_loop(), name="budget"))
        self._tasks.append(asyncio.create_task(self._watch_loop(), name="watch"))

    async def shutdown(self):
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _checkpoint_loop(self):
        from ..telegram.keyboards import persist_repo_ids
        while True:
            await asyncio.sleep(self.s.checkpoint_interval_s)
            try:
                await persist_repo_ids(self.db)
                await self.cp.save()
            except Exception as e:
                log.warning("periodic checkpoint failed: %s", e)

    async def _budget_loop(self):
        if not self.s.in_actions:
            return
        deadline = self.started + self.s.max_run_minutes * 60
        while time.time() < deadline:
            await asyncio.sleep(min(30, max(1, deadline - time.time())))
        await self.handoff(reason="budget")

    async def _watch_loop(self):
        await asyncio.sleep(15)
        while True:
            try:
                await self.poll_watches()
            except Exception:
                log.exception("watch poll failed")
            await asyncio.sleep(60)

    async def poll_watches(self):
        watches = await self.db.list_watches()
        if not watches:
            return
        clients: dict[int, GitHubClient | None] = {}
        try:
            for w in watches:
                uid = w["tg_id"]
                if uid not in clients:
                    clients[uid] = await self.gh_factory(uid)
                gh = clients[uid]
                if gh is None:
                    continue
                try:
                    runs = await gh.list_runs(w["repo"], per_page=5)
                except GitHubError:
                    continue
                if not runs:
                    continue
                latest = runs[0]
                key = f"{latest['id']}:{latest['status']}:{latest.get('conclusion')}"
                if w["last_run_id"] == latest["id"] and w["last_status"] == key:
                    continue
                user = await self.db.get_user(uid)
                lang = user["lang"] if user else "en"
                if w["last_run_id"] is not None:  # first poll just records the baseline
                    changed = [r for r in runs[:3] if r["id"] > (w["last_run_id"] or 0) or
                               (r["id"] == w["last_run_id"] and key != w["last_status"])]
                    for r in reversed(changed):
                        status, concl = r["status"], r.get("conclusion") or ""
                        icon = RUN_ICON.get(concl or status, "🔔")
                        await self.notifier.send(uid, t(lang, "watch_event", icon=icon, repo=w["repo"],
                                                        name=r.get("name", ""), status=status,
                                                        conclusion=f"({concl})" if concl else "",
                                                        branch=r.get("head_branch", ""), event=r.get("event", ""),
                                                        url=r.get("html_url", "")), kind="watch")
                await self.db.update_watch(w["id"], latest["id"], key)
        finally:
            for gh in clients.values():
                if gh:
                    await gh.aclose()

    async def handoff(self, *, reason: str = "manual") -> bool:
        if self.handing_off:
            return False
        self.handing_off = True
        log.info("handoff starting (reason=%s)", reason)
        users = await self.db.all_users()
        for u in users:
            await self.notifier.send(u["tg_id"], t(u["lang"], "lifecycle_bye"), kind="system")
        try:
            from ..telegram.keyboards import persist_repo_ids
            await persist_repo_ids(self.db)
            await self.cp.save(force=True)
        except Exception as e:
            log.error("final checkpoint failed: %s", e)
            for u in users:
                await self.notifier.send(u["tg_id"], t(u["lang"], "export_fail", error=str(e)[:200]), kind="system")
        dispatched = await self.dispatch_next_run()
        if not dispatched and self.s.in_actions:
            log.error("could not dispatch next run — relying on cron watchdog")
        await asyncio.sleep(1)
        await self.stop()
        return dispatched

    async def dispatch_next_run(self) -> bool:
        if not (self.s.in_actions and self.s.gh_pat and self.s.host_repo):
            return False
        async with GitHubClient(self.s.gh_pat) as gh:
            try:
                repo = await gh.get_repo(self.s.host_repo)
                await gh.dispatch_workflow(self.s.host_repo, self.s.workflow_file, repo["default_branch"],
                                           {"reason": "handoff"})
                return True
            except GitHubError as e:
                log.error("dispatch failed: %s", e)
                return False
