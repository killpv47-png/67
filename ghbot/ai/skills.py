"""Skills — on-demand knowledge documents (Hermes ``tools/skills_tool.py`` pattern).

Layout: ``home/skills/<category>/<name>/SKILL.md`` with YAML frontmatter
(``name``, ``description``, optional ``tags``).  Only the compact index goes into
the system prompt (progressive disclosure); the agent loads full content with
``skill_view`` and writes/patches with ``skill_manage``.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .prompt_builder import HOME, scan_context_content

SKILLS_DIR = HOME / "skills"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict = {}
    for line in parts[1].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, parts[2].strip()


def catalog() -> list[dict]:
    out = []
    if not SKILLS_DIR.exists():
        return out
    for md in sorted(SKILLS_DIR.rglob("SKILL.md")):
        meta, _ = _parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
        rel = md.parent.relative_to(SKILLS_DIR)
        category = rel.parts[0] if len(rel.parts) > 1 else "general"
        name = meta.get("name") or md.parent.name
        out.append({"name": name, "description": meta.get("description", "")[:160], "category": category, "path": md})
    return out


def skills_index_block() -> str:
    items = catalog()
    if not items:
        return ""
    by_cat: dict[str, list[str]] = {}
    for s in items:
        by_cat.setdefault(s["category"], []).append(f"    - {s['name']}: {s['description']}")
    lines = [f"  {c}:\n" + "\n".join(v) for c, v in sorted(by_cat.items())]
    return (
        "## Skills\n"
        "Before replying, scan the skills below. If a skill matches or is even partially relevant to your task, you "
        "MUST load it with skill_view(name) and follow its instructions. Err on the side of loading — it is always "
        "better to have context you don't need than to miss critical steps, pitfalls, or established workflows. "
        "Skills encode the user's preferred approach and proven workflows for this project.\n"
        "If a skill has issues, fix it with skill_manage(action='patch'). After difficult/iterative tasks, offer to "
        "save as a skill.\n\n<available_skills>\n" + "\n".join(lines) + "\n</available_skills>\n\n"
        "Only proceed without loading a skill if genuinely none are relevant to the task."
    )


def _find(name: str) -> dict | None:
    for s in catalog():
        if s["name"] == name or s["path"].parent.name == name:
            return s
    return None


def skills_list(category: str | None = None) -> str:
    items = [{k: v for k, v in s.items() if k != "path"} for s in catalog() if not category or s["category"] == category]
    return json.dumps({"skills": items}, ensure_ascii=False)


def skill_view(name: str, file_path: str | None = None) -> str:
    s = _find(name)
    if not s:
        return json.dumps({"success": False, "error": f"skill '{name}' not found", "available": [x["name"] for x in catalog()]})
    base: Path = s["path"].parent
    if file_path:
        target = (base / file_path).resolve()
        if not str(target).startswith(str(base.resolve())) or not target.exists():
            return json.dumps({"success": False, "error": "linked file not found"})
        return json.dumps({"success": True, "name": s["name"], "file": file_path, "content": target.read_text(encoding="utf-8", errors="replace")}, ensure_ascii=False)
    text = s["path"].read_text(encoding="utf-8", errors="replace")
    text = scan_context_content(text, f"skill:{name}")
    linked = {}
    for sub in ("references", "templates", "scripts"):
        d = base / sub
        if d.is_dir():
            linked[sub] = [str(p.relative_to(base)) for p in sorted(d.rglob("*")) if p.is_file()]
    return json.dumps({"success": True, "name": s["name"], "description": s["description"], "content": text, "linked_files": linked}, ensure_ascii=False)


def skill_manage(operations: list[dict]) -> str:
    results = []
    for op in operations or []:
        action = op.get("action")
        name = (op.get("name") or "").strip()
        if not _NAME_RE.match(name):
            results.append({"action": action, "name": name, "success": False, "error": "invalid skill name"})
            continue
        try:
            if action == "create":
                category = re.sub(r"[^a-z0-9_-]", "", (op.get("category") or "general").lower()) or "general"
                d = SKILLS_DIR / category / name
                if (d / "SKILL.md").exists() or _find(name):
                    raise ValueError("skill already exists; use patch")
                content = op.get("content", "")
                if not content.startswith("---"):
                    content = f"---\nname: {name}\ndescription: \"{op.get('description', name)}\"\n---\n\n{content}"
                d.mkdir(parents=True, exist_ok=True)
                (d / "SKILL.md").write_text(content, encoding="utf-8")
                results.append({"action": action, "name": name, "success": True, "path": str(d / "SKILL.md")})
            elif action == "patch":
                s = _find(name)
                if not s:
                    raise ValueError("skill not found")
                target = s["path"] if not op.get("file_path") else (s["path"].parent / op["file_path"])
                if "content" in op and op["content"] is not None:
                    target.write_text(op["content"], encoding="utf-8")
                else:
                    text = target.read_text(encoding="utf-8")
                    old, new = op.get("old_string", ""), op.get("new_string", "")
                    if old not in text:
                        raise ValueError("old_string not found")
                    text = text.replace(old, new) if op.get("replace_all") else text.replace(old, new, 1)
                    target.write_text(text, encoding="utf-8")
                results.append({"action": action, "name": name, "success": True})
            elif action == "write_file":
                s = _find(name)
                if not s:
                    raise ValueError("skill not found")
                target = (s["path"].parent / op["file_path"]).resolve()
                if not str(target).startswith(str(s["path"].parent.resolve())):
                    raise ValueError("path escapes skill dir")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(op.get("file_content", ""), encoding="utf-8")
                results.append({"action": action, "name": name, "success": True})
            elif action == "remove_file":
                s = _find(name)
                if not s:
                    raise ValueError("skill not found")
                target = (s["path"].parent / op["file_path"]).resolve()
                if target.name == "SKILL.md" or not str(target).startswith(str(s["path"].parent.resolve())):
                    raise ValueError("refusing")
                target.unlink(missing_ok=True)
                results.append({"action": action, "name": name, "success": True})
            elif action == "delete":
                s = _find(name)
                if not s:
                    raise ValueError("skill not found")
                shutil.rmtree(s["path"].parent)
                results.append({"action": action, "name": name, "success": True})
            else:
                raise ValueError("unknown action")
        except Exception as e:
            results.append({"action": action, "name": name, "success": False, "error": str(e)})
    return json.dumps({"results": results}, ensure_ascii=False)


SKILLS_LIST_SCHEMA = {
    "name": "skills_list",
    "description": "List available skills (name + description). Use skill_view(name) to load full content.",
    "parameters": {"type": "object", "properties": {"category": {"type": "string", "description": "Optional category filter"}}},
}

SKILL_VIEW_SCHEMA = {
    "name": "skill_view",
    "description": (
        "Load a skill's full SKILL.md content or one of its linked files (references/templates/scripts). "
        "First call returns content plus a 'linked_files' dict; call again with file_path to read one."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "file_path": {"type": "string", "description": "Optional linked file path, e.g. 'references/api.md'"},
        },
        "required": ["name"],
    },
}

SKILL_MANAGE_SCHEMA = {
    "name": "skill_manage",
    "description": (
        "Create, patch, extend or delete skills. The call is an ordered list of operations; each names its target "
        "skill (lowercase, hyphens/underscores). create: content (full SKILL.md with YAML frontmatter) + optional "
        "category. patch: old_string+new_string (or content for a full rewrite). write_file/remove_file: supporting "
        "files. delete: remove the skill."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["create", "patch", "write_file", "remove_file", "delete"]},
                        "name": {"type": "string"},
                        "category": {"type": "string"},
                        "description": {"type": "string"},
                        "content": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                        "replace_all": {"type": "boolean"},
                        "file_path": {"type": "string"},
                        "file_content": {"type": "string"},
                    },
                    "required": ["action", "name"],
                },
            }
        },
        "required": ["operations"],
    },
}
