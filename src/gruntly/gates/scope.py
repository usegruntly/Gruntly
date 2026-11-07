from __future__ import annotations

from pathlib import Path

from .. import worktree as wtmod
from . import matches_any


def check(spec, wt: Path, base: str, root: Path, main_fp_before: str) -> dict:
    violations: list[str] = []
    for path in wtmod.name_status(wt, base):
        if matches_any(path, spec.deny_paths):
            violations.append(f"denied path: {path}")
        elif not matches_any(path, spec.allowed_paths):
            violations.append(f"outside allowed_paths: {path}")
    touched = wtmod.changed_between(root, main_fp_before, wtmod.fingerprint(root))
    violations += [f"main tree modified: {p}" for p in touched]
    return {"ok": not violations, "violations": violations[:20]}
