"""System-prompt assembly — adapted from Hermes Agent ``agent/system_prompt.py`` +
``agent/prompt_builder.py``.

Three ordered tiers, joined with blank lines, built ONCE per session and frozen
(only context compression triggers a rebuild) so provider prefix caching stays warm:

  stable   identity (SOUL.md), tool guidance, execution discipline, platform hint
  context  project context (AGENTS.md), runtime environment
  volatile skills index, MEMORY snapshot, USER snapshot, session line

Guidance blocks are taken from Hermes (lightly edited for this project).
"""

from __future__ import annotations

import os
import platform
import re
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(__file__).parent / "home"
CONTEXT_FILE_MAX_CHARS = 20_000

# ----------------------------------------------------------------- Hermes guidance
DEFAULT_AGENT_IDENTITY = (
    "You are GITHUB_AI, the resident agent of the GitHub Control Bot. Be direct: match the length of your reply "
    "to the weight of the ask — a one-line question gets a one-line answer, and finished work gets a short report "
    "of what changed, what's verified, and what's left, never a replay of the process. No filler, no restating the "
    "request back, no narrating tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly."
)

MEMORY_GUIDANCE = (
    "You have persistent memory, carried across sessions and loaded into each new session's context; the memory "
    "tool's schema defines what belongs there. Skills come first: when you learn something while doing a task — a "
    "procedure, a pitfall, and the user's preferences and corrections for that kind of work — record it in the skill "
    "you used or built for the task (skill_manage), where it loads only when relevant. Memory is the narrow exception "
    "for facts that apply to EVERY session regardless of task (who the user is, environment facts, standing "
    "conventions with no task home); it has a hard character budget, so when it fills, replace or consolidate stale "
    "entries rather than skipping the save. Write entries as declarative facts, not instructions to yourself: 'User "
    "prefers concise responses' ✓ — 'Always respond concisely' ✗. A fact stale within a week belongs in session "
    "history; procedures and workflows belong in skills."
)

SESSION_SEARCH_GUIDANCE = (
    "When the user references something from a past conversation or you suspect relevant cross-session context "
    "exists, use session_search to recall it before asking them to repeat themselves."
)

SKILL_SAFETY_HEADING = "## Skill Safety Rule"
SKILLS_GUIDANCE = (
    "When you work out a non-trivial workflow, record it with skill_manage for future reuse.\n\n"
    f"{SKILL_SAFETY_HEADING}\n"
    "A skill placeholder containing `[SKILL_PRUNED]` lost its content in context compression and is inaccessible — "
    "reload it with skill_view(name='...') before acting on anything that depends on it."
)

TOOL_USE_ENFORCEMENT_GUIDANCE = (
    "# Tool-use enforcement\n"
    "You MUST use your tools to take action — do not describe what you would do or plan to do without actually doing "
    "it. When you say you will perform an action, you MUST immediately make the corresponding tool call in the same "
    "response. Never end your turn with a promise of future action — execute it now.\n"
    "Keep working until the task is actually complete. Every response should either (a) contain tool calls that make "
    "progress, or (b) deliver a final result to the user."
)

TASK_COMPLETION_GUIDANCE = (
    "# Finishing the job\n"
    "When the user asks you to build, run, or verify something, the deliverable is a working artifact backed by real "
    "tool output — not a description of one. Do not stop after writing a stub, a plan, or a single command. Keep "
    "working until you have actually exercised the code or produced the requested result, then report what real "
    "execution returned.\n"
    "If a tool, install, or network call fails and blocks the real path, say so directly and try an alternative. "
    "NEVER substitute plausible-looking fabricated output for results you couldn't actually produce. Reporting a "
    "blocker honestly is always better than inventing a result."
)

PARALLEL_TOOL_CALL_GUIDANCE = (
    "# Parallel tool calls\n"
    "When you need several pieces of information that don't depend on each other, request them together in a "
    "single response instead of one tool call per turn. Independent reads, searches, web fetches, and read-only "
    "commands should be batched into the same assistant turn. Only serialize calls when a later call genuinely "
    "depends on an earlier call's result."
)

STEPWISE_GUIDANCE = (
    "# Step-by-step execution\n"
    "The user wants to see progress one verified step at a time. For any task with 3+ steps: (1) write the plan with "
    "todo_list, (2) mark exactly one item in_progress, (3) execute it with tools, (4) mark it completed only after a "
    "tool result proves it, (5) move on. If a step fails, record the error, cancel the item and add a revised one. "
    "Dangerous operations (delete repository, force push, wipe repo files, delete secrets) require the user's explicit "
    "confirmation earlier in this conversation — if absent, ask and stop."
)

SECRETS_GUIDANCE = (
    "# Secrets hygiene\n"
    "Never print, store, or summarize secret values (PATs, API keys, STATE_KEY, BOT_TOKEN, repo secret values). "
    "Refer to them by name only. Tool outputs are redacted automatically but you must not try to reconstruct them."
)

PLATFORM_HINT_TELEGRAM = (
    "You are on Telegram. Use HTML-safe plain text: **bold** and `code` convert automatically; avoid tables (use "
    "bullets or labeled lines). Keep messages under ~3500 characters; split long answers. The user controls the bot "
    "through buttons as well — when a UI flow exists (e.g. uploading a ZIP, setting a secret) you may point to it, "
    "but you can also perform the operation yourself with github_api."
)


# ----------------------------------------------------------------- context files
def _truncate(content: str, name: str, max_chars: int = CONTEXT_FILE_MAX_CHARS) -> str:
    if len(content) <= max_chars:
        return content
    head = int(max_chars * 0.7)
    tail = int(max_chars * 0.2)
    return content[:head] + f"\n\n[... {name} truncated ({len(content) - head - tail} chars omitted) ...]\n\n" + content[-tail:]


_INJECTION_PATTERNS = [
    re.compile(r"ignore (all )?(previous|prior|above) instructions", re.I),
    re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]{3,}"),
]


def scan_context_content(content: str, filename: str) -> str:
    """Prompt-injection guard for context/skill files (Hermes _scan_context_content)."""
    for p in _INJECTION_PATTERNS:
        if p.search(content):
            return f"[BLOCKED: {filename} contained suspicious instructions and was not loaded]"
    return content


def load_soul() -> str:
    p = HOME / "SOUL.md"
    if p.exists():
        return _truncate(p.read_text(encoding="utf-8").strip(), "SOUL.md")
    return DEFAULT_AGENT_IDENTITY


def load_project_context() -> str:
    p = HOME / "AGENTS.md"
    if not p.exists():
        return ""
    content = scan_context_content(p.read_text(encoding="utf-8").strip(), "AGENTS.md")
    return "# Project Context\n\nThe following project context files have been loaded and should be followed:\n\n## AGENTS.md\n" + _truncate(content, "AGENTS.md")


def runtime_environment(workspace: Path, *, in_actions: bool, host_repo: str, run_id: str) -> str:
    lines = [
        "# GITHUB_AI runtime environment",
        f"Host: {platform.system()} {platform.machine()}, Python {platform.python_version()}",
        f"Working directory (terminal cwd): {workspace}",
        f"Repository source root: {os.environ.get('GITHUB_WORKSPACE') or Path.cwd()}",
    ]
    if in_actions:
        lines.append(f"Running inside GitHub Actions: repo={host_repo} run_id={run_id}. The runner is ephemeral — "
                     "anything not committed/pushed or stored in the bot DB is lost when the run ends.")
    else:
        lines.append("Running locally (not in GitHub Actions).")
    lines.append("<!-- End GITHUB_AI runtime environment -->")
    return "\n".join(lines)


# ----------------------------------------------------------------- assembly
def build_system_prompt(
    *,
    model: str,
    session_id: str,
    skills_index: str,
    memory_block: str,
    user_block: str,
    workspace: Path,
    in_actions: bool,
    host_repo: str,
    run_id: str,
    has_web_search: bool,
    github_login: str,
    access_level: str,
) -> str:
    stable = [
        load_soul(),
        MEMORY_GUIDANCE,
        SESSION_SEARCH_GUIDANCE,
        SKILLS_GUIDANCE,
        TOOL_USE_ENFORCEMENT_GUIDANCE,
        TASK_COMPLETION_GUIDANCE,
        PARALLEL_TOOL_CALL_GUIDANCE,
        STEPWISE_GUIDANCE,
        SECRETS_GUIDANCE,
        PLATFORM_HINT_TELEGRAM,
    ]
    context = [load_project_context()]
    tools_note = (
        "# Available capability summary\n"
        "terminal (shell in workspace), read_file / write_file / patch / search_files, github_api (authenticated as "
        f"@{github_login}, access level {access_level}), "
        + ("web_search + web_extract (Tavily), " if has_web_search else "")
        + "memory, skills_list / skill_view / skill_manage, session_search, todo_list."
    )
    context.append(tools_note)
    volatile = [
        skills_index,
        memory_block,
        user_block,
        f"Conversation started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\nSession: {session_id}\nModel: {model}",
        runtime_environment(workspace, in_actions=in_actions, host_repo=host_repo, run_id=run_id),
    ]
    parts = [p for p in stable + context + volatile if p and p.strip()]
    return "\n\n".join(parts)
