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


def pick_installed() -> str | None:
    """The first parent harness found on this machine, or None."""
    for name in names():
        if get_parent(name).detect().installed:
            return name
    return None
