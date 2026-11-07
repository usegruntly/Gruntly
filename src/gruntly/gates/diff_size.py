from __future__ import annotations

from pathlib import Path

from .. import worktree as wtmod

MAX_FILE_BYTES = 1_000_000


def check(spec, wt: Path, base: str) -> dict:
    limit = int(spec.gates.get("diff_max_lines") or 0)
    rows = wtmod.numstat(wt, base)
    lines = sum((a or 0) + (d or 0) for _, a, d in rows)
    problems = [f"binary file: {p}" for p, a, _ in rows if a is None]
    for p, _, _ in rows:
        f = wt / p
        if f.is_file() and f.stat().st_size > MAX_FILE_BYTES:
            problems.append(f"file over {MAX_FILE_BYTES} bytes: {p}")
    if limit and lines > limit:
        problems.append(f"{lines} changed lines exceeds limit {limit}")
    out = {"ok": not problems, "lines": lines}
    if problems:
        out["problems"] = problems[:10]
    return out
