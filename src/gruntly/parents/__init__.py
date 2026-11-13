"""Parent adapters: one interface for every harness that can read a task and call gruntly (delegating) or do the job itself (working)."""
from __future__ import annotations

from .base import MODES, ParentAdapter, ParentCaps, ParentCommand, ParentOutcome, RunResult, check_mode, run  # noqa: F401


def table() -> dict[str, type]:
    from .claude import ClaudeParent
    return {"claude": ClaudeParent}


def names() -> list[str]:
    return list(table())


def get_parent(name: str) -> ParentAdapter:
    t = table()
    try:
        return t[name]()
    except KeyError:
        raise ValueError(f"unknown parent harness {name!r}; known: {', '.join(t)}") from None


def settings(root=None) -> dict:
    """The `[parent]` table of your global settings, then the project's `.gruntly.toml` (the project wins): harness, model, provider, mode."""
    from pathlib import Path
    from ..spec import _toml, global_config_path
    out: dict = {}
    for p in (global_config_path(), Path(root) / ".gruntly.toml" if root else None):
        if p is not None and p.is_file():
            t = _toml(p).get("parent")
            if isinstance(t, dict):
                out.update({k: v for k, v in t.items() if k in ("harness", "model", "provider", "mode") and v})
    return out


def resolve(parent: str | None = None, model: str | None = None, provider: str | None = None, mode: str | None = None, root=None) -> dict:
    """What to launch: a flag, else the `[parent]` settings, else the first parent harness installed here (claude if none), mode delegating."""
    s = settings(root)
    return {"parent": parent or s.get("harness") or pick_installed() or "claude", "model": model or s.get("model"),
            "provider": provider or s.get("provider"), "mode": mode or s.get("mode") or "delegating"}


def pick_installed() -> str | None:
    """The first parent harness found on this machine, or None."""
    for name in names():
        if get_parent(name).detect().installed:
            return name
    return None
