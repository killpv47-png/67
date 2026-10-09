"""Runtime configuration.

Everything comes from environment variables so the same code runs identically in
GitHub Actions, Docker, or a bare VPS.  Only ``BOT_TOKEN`` and ``STATE_KEY`` are
mandatory; everything else has a safe default.

Secret inventory (also mirrored in ai/home/AGENTS.md so GITHUB_AI knows where things live):
  BOT_TOKEN       Telegram bot token (BotFather)
  STATE_KEY       32+ char passphrase used to encrypt the SQLite checkpoint + every stored PAT
  GH_PAT          GitHub token of the *host* repo (the repo running the workflow). Used ONLY by
                  the lifecycle module to push the encrypted checkpoint and dispatch the next run.
  TAVILY_API_KEY  (optional) enables web_search for GITHUB_AI. The user asked for the name
                  "TAVILY" — both TAVILY and TAVILY_API_KEY are accepted.
  OWNER_IDS       (optional) comma separated Telegram user ids allowed to use the bot.
                  Empty = first user to /start becomes owner (then locked).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(*names: str, default: str = "") -> str:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v.strip()
    return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class Settings:
    bot_token: str = field(default_factory=lambda: _env("BOT_TOKEN", "TELEGRAM_BOT_TOKEN"))
    state_key: str = field(default_factory=lambda: _env("STATE_KEY"))
    gh_pat: str = field(default_factory=lambda: _env("GH_PAT"))
    tavily_key: str = field(default_factory=lambda: _env("TAVILY_API_KEY", "TAVILY"))
    owner_ids: tuple[int, ...] = field(
        default_factory=lambda: tuple(
            int(x) for x in _env("OWNER_IDS").replace(";", ",").split(",") if x.strip().isdigit()
        )
    )

    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", default="data")))
    workspace_dir: Path = field(default_factory=lambda: Path(_env("WORKSPACE_DIR", default="data/workspace")))

    # GitHub Actions context (auto-populated by the runner)
    host_repo: str = field(default_factory=lambda: _env("GITHUB_REPOSITORY"))
    run_id: str = field(default_factory=lambda: _env("GITHUB_RUN_ID"))
    run_attempt: str = field(default_factory=lambda: _env("GITHUB_RUN_ATTEMPT", default="1"))
    workflow_file: str = field(default_factory=lambda: _env("WORKFLOW_FILE", default="bot.yml"))
    in_actions: bool = field(default_factory=lambda: _env("GITHUB_ACTIONS").lower() == "true")

    # Lifecycle: GitHub Actions hard-kills a job at 6h. We hand off well before that.
    max_run_minutes: int = field(default_factory=lambda: _int("MAX_RUN_MINUTES", 330))
    checkpoint_interval_s: int = field(default_factory=lambda: _int("CHECKPOINT_INTERVAL", 120))
    handoff_delay_s: int = field(default_factory=lambda: _int("HANDOFF_DELAY", 20))

    # AI defaults
    ai_max_iterations: int = field(default_factory=lambda: _int("AI_MAX_ITERATIONS", 60))
    ai_tool_timeout_s: int = field(default_factory=lambda: _int("AI_TOOL_TIMEOUT", 180))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", default="INFO"))

    def validate(self) -> list[str]:
        problems = []
        if not self.bot_token:
            problems.append("BOT_TOKEN is missing")
        if len(self.state_key) < 16:
            problems.append("STATE_KEY must be at least 16 characters (used to encrypt tokens and checkpoints)")
        return problems

    @property
    def db_path(self) -> Path:
        return self.data_dir / "ghbot.db"


settings = Settings()
