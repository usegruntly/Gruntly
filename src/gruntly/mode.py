"""Whether gruntly may be used right now: a switch, so nobody has to repeat "use gruntly" or "don't use gruntly" in every chat.

    auto   the skill decides when delegating pays (the default, and what gruntly did before there was a switch)
    on     delegate every eligible change without asking
    off    never: gruntly refuses new work and the parent does it itself

Where it is set, most specific first: the environment (GRUNTLY_MODE), this Claude Code session
(`.gruntly/sessions/<session id>.mode`), this project (`.gruntly/mode`), then auto. Both files live under `.gruntly/`, which git
ignores, so a mode is personal and never lands in a commit. The Claude Code `/gruntly` command writes the same files, so the
two always agree; the CLI is what enforces `off`, whichever agent is calling it.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

MODES = ("auto", "on", "off")
SESSION_KEEP_DAYS = 14


def _read(p: Path) -> str | None:
    try:
        v = p.read_text(encoding="utf8").strip().lower()
    except OSError:
        return None
    return v if v in MODES else None


def session_id() -> str | None:
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or None


def session_file(root: Path, sid: str) -> Path:
    return root / ".gruntly" / "sessions" / f"{sid}.mode"


def project_file(root: Path) -> Path:
    return root / ".gruntly" / "mode"


def resolve(root: Path) -> tuple[str, str]:
    """(mode, where it came from): environment, session, project, or default."""
    env = (os.environ.get("GRUNTLY_MODE") or "").strip().lower()
    if env in MODES:
        return env, "environment"
    sid = session_id()
    if sid:
        v = _read(session_file(root, sid))
        if v:
            return v, "session"
    v = _read(project_file(root))
    if v:
        return v, "project"
    return "auto", "default"


def set_mode(root: Path, mode: str, scope: str = "project") -> Path:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    if scope == "session":
        sid = session_id()
        if not sid:
            raise ValueError("no session id: --session only works inside Claude Code (use --project, or set the mode with /gruntly)")
        path = session_file(root, sid)
        _prune_sessions(path.parent)
    elif scope == "project":
        path = project_file(root)
    else:
        raise ValueError("scope must be session or project")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mode + "\n", encoding="utf8")
    return path


def _prune_sessions(folder: Path) -> None:
    """Session files of chats that are long over: drop them so the folder does not grow forever."""
    cutoff = time.time() - SESSION_KEEP_DAYS * 86400
    try:
        for f in folder.glob("*.mode"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def refusal(root: Path) -> str | None:
    """The one-line message a caller gets when gruntly is off, or None when it may run."""
    mode, where = resolve(root)
    if mode != "off":
        return None
    scope = {"session": "this Claude Code session", "project": "this project",
             "environment": "the environment (GRUNTLY_MODE)"}.get(where, where)
    return (f"gruntly is switched OFF for {scope}: do this change yourself, directly, and do not try gruntly again in this chat. "
            "(The person turns it back on with /gruntly on, or `gruntly mode on`.)")
