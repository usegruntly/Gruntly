"""Where a holdout test lives while a run needs it.

A holdout is the parent's own test of a behaviour the existing tests miss. It is needed for one check, so gruntly keeps the text
it receives on stdin inside the run's own record (`spec.json` under `.gruntly/runs/`, removed by `gruntly gc`) and writes it into a
copy of the project only for the moment the check runs. Nothing is left in the user's project (2026-11-14: a day of runs left 21
`holdout_*.py` files, 18 with local paths, in a repo root).
"""
from __future__ import annotations

import shutil
from pathlib import Path


def place(h: dict, dest: Path, source: Path | None = None) -> list[Path]:
    """Put the holdout's files under `dest` and return the ones this call created (so the caller removes exactly those).
    Text kept in the run record is written; a file the parent wrote into the project is copied from `source` when that is another tree.
    A name that already exists in `dest` is an error, never an overwrite."""
    inline = h.get("inline") or {}
    made: list[Path] = []
    try:
        for rel in h["files"]:
            dst = Path(dest) / rel
            if rel in inline:
                if dst.exists():
                    raise FileExistsError(f"holdout {rel}: a file with that name already exists in the project; use another name")
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(inline[rel].encode("utf8"))
                made.append(dst)
            elif source is not None and Path(source).resolve() != Path(dest).resolve():
                src = Path(source) / rel
                if not src.is_file():
                    raise FileNotFoundError(f"holdout file missing: {rel}")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                made.append(dst)
            elif not dst.is_file():
                raise FileNotFoundError(f"holdout file missing: {rel}")
    except BaseException:
        remove(made)
        raise
    return made


def remove(made: list[Path]) -> None:
    for f in made:
        f.unlink(missing_ok=True)
