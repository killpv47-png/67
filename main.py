"""GitHub Control Bot — entry point.

Startup order:
  1. settings + logging
  2. restore encrypted checkpoint (needs GH_PAT) BEFORE opening the DB
  3. open DB, build bot, lifecycle manager
  4. announce, resume pending AI tasks, start polling
  5. on handoff/stop: final checkpoint already done by lifecycle; exit 0
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from ghbot.core.config import settings
from ghbot.core.db import Database
from ghbot.core.logging_setup import setup_logging
from ghbot.core.redact import register_secret
from ghbot.lifecycle import Checkpointer, LifecycleManager
from ghbot.telegram.bot import build, set_commands
from ghbot.telegram.handlers.ai_chat import resume_pending
from ghbot.telegram.keyboards import load_repo_ids

log = logging.getLogger("main")
HOME = Path(__file__).parent / "ghbot" / "ai" / "home"


async def run() -> int:
    setup_logging(settings.log_level)
    problems = settings.validate()
    if problems:
        for p in problems:
            log.error(p)
        return 2
    for s in (settings.bot_token, settings.state_key, settings.gh_pat, settings.tavily_key):
        register_secret(s)

    db = Database(settings.db_path)
    cp = Checkpointer(db, host_repo=settings.host_repo, gh_pat=settings.gh_pat, state_key=settings.state_key, home_dir=HOME)
    restored = await cp.restore_if_needed()
    log.info("checkpoint: %s", restored)
    await db.open()
    await load_repo_ids(db)  # inline buttons from before the restart keep working

    bot, dp, app = build(settings, db)
    stop_event = asyncio.Event()

    async def stop():
        stop_event.set()

    async def gh_factory(tg_id: int):
        return await app.gh(tg_id)

    lifecycle = LifecycleManager(settings, db, app.notifier, cp, stop=stop, gh_factory=gh_factory)
    app.lifecycle = lifecycle

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(lifecycle.handoff(reason="signal")))
        except NotImplementedError:  # pragma: no cover
            pass

    try:
        await set_commands(bot)
    except Exception as e:
        log.warning("set_commands failed: %s", e)
    await bot.delete_webhook(drop_pending_updates=False)

    await lifecycle.start(restored)
    try:
        await resume_pending(app)
    except Exception:
        log.exception("resume_pending failed")

    polling = asyncio.create_task(dp.start_polling(bot, handle_signals=False, allowed_updates=["message", "callback_query"]))
    log.info("bot online (run=%s, actions=%s)", settings.run_id or "local", settings.in_actions)

    # Wait for either a requested stop (handoff/signal) or the poller dying (bad token, network wall).
    stop_waiter = asyncio.create_task(stop_event.wait())
    done, _ = await asyncio.wait({stop_waiter, polling}, return_when=asyncio.FIRST_COMPLETED)
    exit_code = 0
    if polling in done and not stop_event.is_set():
        exc = polling.exception() if not polling.cancelled() else None
        log.error("polling stopped unexpectedly: %s", exc)
        exit_code = 1  # red run; the cron watchdog restarts us
        if not lifecycle.handing_off:
            try:
                await cp.save(force=True)  # never lose state, even on a crash
            except Exception as e:
                log.error("emergency checkpoint failed: %s", e)
    stop_waiter.cancel()
    log.info("stopping polling…")
    try:
        await dp.stop_polling()
    except Exception:
        pass
    try:
        await asyncio.wait_for(polling, timeout=15)
    except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
        polling.cancel()
    await lifecycle.shutdown()
    for agent in app.agents.values():
        try:
            await agent.close()
        except Exception:
            pass
    await db.close()
    await bot.session.close()
    log.info("bye")
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(run()))
    except KeyboardInterrupt:
        sys.exit(0)
