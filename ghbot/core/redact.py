"""Redact secrets before anything reaches Telegram, logs, memory, or the AI summary.

Mirrors Hermes' ``agent/redact.py`` idea: pattern-based, conservative, and applied
at every output boundary (notifications, tool results, compaction summaries).
"""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),               # GitHub PATs (classic + fine-grained prefix family)
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),                     # OpenAI-style keys
    re.compile(r"\btvly-[A-Za-z0-9_\-]{10,}\b"),                   # Tavily
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"),                # Telegram bot tokens
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                           # AWS
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),               # Slack
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{20,}"),           # Authorization headers
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd)\s*[=:]\s*['\"]?([A-Za-z0-9._\-]{12,})"),
]

_KNOWN: set[str] = set()


def register_secret(value: str | None) -> None:
    """Register an exact secret value so it is always masked regardless of shape."""
    if value and len(value) >= 8:
        _KNOWN.add(value)


def redact(text: str) -> str:
    if not text:
        return text
    for s in _KNOWN:
        text = text.replace(s, "[REDACTED]")
    for p in _PATTERNS:
        if p.groups >= 2:
            text = p.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
        elif p.groups == 1:
            text = p.sub(lambda m: f"{m.group(1)} [REDACTED]", text)
        else:
            text = p.sub("[REDACTED]", text)
    return text
