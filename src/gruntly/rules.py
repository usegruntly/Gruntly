"""The person's own rules for a project, noted by the parent agent, read by every child and every reviewer.

`.gruntly/rules.md` (the project) and `.gruntly/sessions/<id>.rules.md` (one Claude Code session) hold short rules the
person stated ("do not change the public API of tool/cli.py"), one `- ` line each. The parent adds a line when the person
states a lasting rule about the code and removes it when they lift it (`gruntly rules add|remove`).

A `## Read with these rules` section lists project files (CLAUDE.md, AGENTS.md) whose text a reviewer gets along with the
rules. With no rules file, the CLAUDE.md and AGENTS.md at the repository root are used. `@path` lines inside those files
are followed once, duplicates are dropped, and the total is capped so a huge file cannot crowd out the change under review.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

HEADER = ("# gruntly rules\n"
          "Rules the person stated for this project, one per line. Children and reviewers follow them.\n\n")
READ_WITH = "## Read with these rules"
DEFAULT_FILES = ("CLAUDE.md", "AGENTS.md")
ATTACH_MAX_CHARS = 32_000          # about 8k tokens of CLAUDE.md / AGENTS.md text for a reviewer
IMPORT = re.compile(r"^@(\S+)\s*$", re.M)


def project_file(root: Path) -> Path:
    return Path(root) / ".gruntly" / "rules.md"


def session_file(root: Path) -> Path | None:
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    return Path(root) / ".gruntly" / "sessions" / f"{sid}.rules.md" if sid else None


def _lines(path: Path | None) -> list[str]:
    if not path or not path.is_file():
        return []
    text = path.read_text(encoding="utf8", errors="replace").split(READ_WITH, 1)[0]
    return [ln[2:].strip() for ln in text.splitlines() if ln.startswith("- ") and ln[2:].strip()]


def _read_with(root: Path) -> list[str]:
    p = project_file(root)
    if not p.is_file():
        return [f for f in DEFAULT_FILES if (Path(root) / f).is_file()]
    text = p.read_text(encoding="utf8", errors="replace")
    if READ_WITH not in text:
        return [f for f in DEFAULT_FILES if (Path(root) / f).is_file()]
    section = text.split(READ_WITH, 1)[1]
    return [ln[2:].strip().strip("`") for ln in section.splitlines() if ln.startswith("- ")]


def person_rules(root: Path) -> str:
    """The person's rules (project, then this session) as `- ` lines; empty when there are none."""
    seen, out = set(), []
    for ln in _lines(project_file(root)) + _lines(session_file(root)):
        if ln not in seen:
            seen.add(ln)
            out.append(f"- {ln}")
    return "\n".join(out)


def attached(root: Path, limit: int = ATTACH_MAX_CHARS) -> str:
    """CLAUDE.md / AGENTS.md (or the listed files) with `@path` imports followed once, for a reviewer."""
    root = Path(root).resolve()
    done: set[Path] = set()
    parts: list[str] = []
    used = 0

    def add(rel: str, depth: int = 0) -> None:
        nonlocal used
        p = (root / rel).resolve()
        if p in done or depth > 3 or not p.is_file() or not p.is_relative_to(root):
            return
        done.add(p)
        text = p.read_text(encoding="utf8", errors="replace")
        body = IMPORT.sub("", text).strip()
        if body:
            room = limit - used
            if room <= 200:
                parts.append(f"[{rel}: left out, the attached files already reached {limit} characters]")
                return
            shown = body if len(body) <= room else body[:room] + f"\n[... {rel} cut at {room} of {len(body)} characters]"
            used += len(shown)
            parts.append(f"=== {rel} ===\n{shown}")
        for imp in IMPORT.findall(text):
            add(str((p.parent / imp).resolve().relative_to(root)) if (p.parent / imp).exists() else imp, depth + 1)

    for f in _read_with(root):
        add(f)
    return "\n\n".join(parts)


def _write(path: Path, rules: list[str], read_with: list[str] | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = HEADER + "".join(f"- {r}\n" for r in rules)
    if read_with is not None:
        body += f"\n{READ_WITH}\n" + "".join(f"- {f}\n" for f in read_with)
    path.write_text(body, encoding="utf8", newline="\n")


def add(root: Path, rule: str, session: bool = False) -> Path:
    rule = " ".join(rule.split())
    if not rule:
        raise ValueError("the rule is empty")
    if not re.search(r"\(\d{4}-\d{2}-\d{2}\)$", rule):
        rule += f" ({time.strftime('%Y-%m-%d')})"
    path = session_file(root) if session else project_file(root)
    if path is None:
        raise ValueError("no Claude Code session here (CLAUDE_CODE_SESSION_ID is not set): add it to the project instead")
    current = _lines(path)
    keep_read = _read_with(root) if not session else None
    if rule not in current:
        current.append(rule)
    _write(path, current, keep_read)
    return path


def remove(root: Path, what: str, session: bool = False) -> list[str]:
    """Remove rules by number (1-based, as `gruntly rules` lists them) or by text they contain. Returns what was removed."""
    path = session_file(root) if session else project_file(root)
    current = _lines(path)
    if what.isdigit() and 1 <= int(what) <= len(current):
        gone = [current.pop(int(what) - 1)]
    else:
        gone = [r for r in current if what.lower() in r.lower()]
        current = [r for r in current if r not in gone]
    if gone and path is not None:
        _write(path, current, None if session else _read_with(root))
    return gone
