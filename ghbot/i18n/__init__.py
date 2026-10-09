"""Tiny i18n layer.  ``t(lang, key, **kw)`` with English fallback.

Languages: en (primary), fa (complete second), ru, ar, tr, es, de, fr, zh, hi.
"""

from __future__ import annotations

import logging

from .en import STRINGS as EN
from .fa import STRINGS as FA
from .others import STRINGS_BY_LANG

log = logging.getLogger(__name__)

LANGS: dict[str, dict[str, str]] = {"en": EN, "fa": FA, **STRINGS_BY_LANG}

LANG_NAMES = {
    "en": "🇬🇧 English",
    "fa": "🇮🇷 فارسی",
    "ar": "🇸🇦 العربية",
    "ru": "🇷🇺 Русский",
    "tr": "🇹🇷 Türkçe",
    "es": "🇪🇸 Español",
    "de": "🇩🇪 Deutsch",
    "fr": "🇫🇷 Français",
    "zh": "🇨🇳 中文",
    "hi": "🇮🇳 हिन्दी",
}

RTL = {"fa", "ar"}


def t(__lang: str, __key: str, /, **kw) -> str:
    """Translate ``key`` for ``lang``.  Positional-only so format placeholders may be
    called ``lang``/``key`` too (e.g. ``t(code, "lang_set", lang="فارسی")``)."""
    table = LANGS.get(__lang) or EN
    s = table.get(__key)
    if s is None:
        s = EN.get(__key)
        if s is None:
            log.warning("missing i18n key %s", __key)
            return __key
    if not kw:
        return s
    try:
        return s.format(**kw)
    except (KeyError, IndexError, ValueError):
        # a missing placeholder must never crash a handler — fill what we can
        return _safe_format(s, kw)


def _safe_format(s: str, kw: dict) -> str:
    class _D(dict):
        def __missing__(self, k):
            return "{" + k + "}"
    try:
        return s.format_map(_D(kw))
    except Exception:
        return s


def missing_keys(lang: str) -> list[str]:
    return [k for k in EN if k not in LANGS.get(lang, {})]
