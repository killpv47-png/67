"""Token access-level classification.

GitHub returns the granted scopes of a classic PAT in the ``X-OAuth-Scopes``
header.  Fine-grained tokens return no scopes header at all; for those we probe
a few endpoints to infer what works.

Levels (highest first):
  GOD        full control: repo + workflow + admin:org + delete_repo + user + admin:public_key …
  ARCHITECT  repo + workflow + delete_repo (can build & destroy anything repo-level)
  ENGINEER   repo + workflow (can push code, manage secrets, run Actions)
  DEVELOPER  repo only (code + secrets, but can't edit workflow files)
  OBSERVER   read-only scopes (public_repo / read:*)
  GHOST      token valid but essentially no useful permission
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessLevel:
    name: str
    emoji: str
    rank: int
    can_write_repo: bool
    can_workflow: bool
    can_delete: bool
    can_admin: bool
    description_key: str  # i18n key


LEVELS = {
    "GOD": AccessLevel("GOD", "👑", 6, True, True, True, True, "access_god"),
    "ARCHITECT": AccessLevel("ARCHITECT", "🏛", 5, True, True, True, False, "access_architect"),
    "ENGINEER": AccessLevel("ENGINEER", "🛠", 4, True, True, False, False, "access_engineer"),
    "DEVELOPER": AccessLevel("DEVELOPER", "💻", 3, True, False, False, False, "access_developer"),
    "OBSERVER": AccessLevel("OBSERVER", "👁", 2, False, False, False, False, "access_observer"),
    "GHOST": AccessLevel("GHOST", "👻", 1, False, False, False, False, "access_ghost"),
}

_ADMIN_SCOPES = {"admin:org", "admin:public_key", "admin:repo_hook", "admin:org_hook", "admin:gpg_key", "admin:enterprise"}


def classify_access(scopes: list[str] | None, *, fine_grained_probe: dict | None = None) -> AccessLevel:
    """Return the AccessLevel for a set of classic scopes, or a fine-grained probe result.

    ``fine_grained_probe`` keys: can_read, can_write, can_workflow, can_delete, can_admin
    """
    if scopes is None and fine_grained_probe is not None:
        p = fine_grained_probe
        if p.get("can_admin") and p.get("can_delete") and p.get("can_workflow"):
            return LEVELS["GOD"]
        if p.get("can_delete") and p.get("can_workflow"):
            return LEVELS["ARCHITECT"]
        if p.get("can_workflow") and p.get("can_write"):
            return LEVELS["ENGINEER"]
        if p.get("can_write"):
            return LEVELS["DEVELOPER"]
        if p.get("can_read"):
            return LEVELS["OBSERVER"]
        return LEVELS["GHOST"]

    s = {x.strip() for x in (scopes or []) if x.strip()}
    has_repo = "repo" in s
    has_workflow = "workflow" in s
    has_delete = "delete_repo" in s

    if has_repo and has_workflow and has_delete and (s & _ADMIN_SCOPES or "user" in s):
        return LEVELS["GOD"]
    if has_repo and has_workflow and has_delete:
        return LEVELS["ARCHITECT"]
    if has_repo and has_workflow:
        return LEVELS["ENGINEER"]
    if has_repo:
        return LEVELS["DEVELOPER"]
    if s & {"public_repo", "read:org", "read:user", "read:packages", "read:project"}:
        return LEVELS["OBSERVER"]
    return LEVELS["GHOST"]
