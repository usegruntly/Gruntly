"""On-disk run records under <repo>/.gruntly/runs/<id>/ plus a JSONL index in the state dir."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

RETENTION_DAYS = 14
RETENTION_RUNS = 50


def state_dir() -> Path:
    base = os.environ.get("GRUNTLY_STATE_DIR")
    return Path(base) if base else Path.home() / ".local" / "state" / "gruntly"


def force_rmtree(path: Path) -> None:
    """rmtree that also removes read-only files (git packs inside a harness's state dir on Windows)."""
    import stat

    def _writable(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onerror=_writable)


class RunNotFound(KeyError):
    pass


class Store:
    def __init__(self, root: Path, run_id: str):
        self.root, self.run_id = Path(root), run_id
        self.dir = self.root / ".gruntly" / "runs" / run_id

    @classmethod
    def existing(cls, root: Path, run_id: str) -> "Store":
        s = cls(root, run_id)
        if not s.dir.is_dir():
            raise RunNotFound(run_id)
        return s

    def create(self, spec_dict: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.write_json("spec.json", spec_dict)
        self.set_state("queued")

    # json helpers
    def write_json(self, name: str, data) -> None:
        (self.dir / name).write_text(json.dumps(data, indent=2), encoding="utf8")

    def read_json(self, name: str, default=None):
        p = self.dir / name
        return json.loads(p.read_text(encoding="utf8")) if p.exists() else default

    def write_text(self, name: str, text: str) -> None:
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf8")

    def append_text(self, name: str, text: str) -> None:
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf8") as f:
            f.write(text)

    def read_text(self, name: str) -> str:
        p = self.dir / name
        return p.read_text(encoding="utf8", errors="replace") if p.exists() else ""

    # state
    def set_state(self, state: str, **extra) -> None:
        cur = self.read_json("status.json", {})
        cur.update({"state": state, "updated": time.time(), **extra})
        cur.setdefault("created", cur["updated"])
        self.write_json("status.json", cur)

    def status(self) -> dict:
        s = self.read_json("status.json", {"state": "unknown"})
        s["elapsed_s"] = round(time.time() - s.get("created", time.time()), 1) if s["state"] != "done" \
            else round(s.get("updated", 0) - s.get("created", 0), 1)
        return {"run_id": self.run_id, **s}

    def save_result(self, result: dict, meta: dict | None = None) -> None:
        meta = meta or {}
        self.write_json("result.json", result)
        self.set_state("done")
        idx = state_dir()
        idx.mkdir(parents=True, exist_ok=True)
        line = {"ts": time.time(), "repo": str(self.root), "run_id": self.run_id,
                "status": result.get("status"), "attempts": result.get("attempts"),
                "harness": (self.read_json("spec.json") or {}).get("harness"),
                "model": (self.read_json("spec.json") or {}).get("model"),
                "wall_s": meta.get("wall_s", result.get("wall_s")), "ctx": self.read_json("status.json", {}).get("ctx"),
                "profile": self.read_json("status.json", {}).get("profile"),
                "result_bytes": len(json.dumps(result)), "child_usage": meta.get("child_usage")}
        with (idx / "runs.jsonl").open("a", encoding="utf8") as f:
            f.write(json.dumps(line) + "\n")


def list_runs(root: Path) -> list[str]:
    d = Path(root) / ".gruntly" / "runs"
    return sorted((p.name for p in d.iterdir() if p.is_dir()), key=lambda n: (d / n).stat().st_mtime) if d.is_dir() else []


def read_index() -> list[dict]:
    p = state_dir() / "runs.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def gc(root: Path, remove_worktree, days: int = RETENTION_DAYS, keep: int = RETENTION_RUNS) -> list[str]:
    """Drop run records past retention and any worktree without a record."""
    removed = []
    runs = list_runs(root)
    cutoff = time.time() - days * 86400
    for i, rid in enumerate(runs):
        old = (Path(root) / ".gruntly" / "runs" / rid).stat().st_mtime < cutoff
        if old or i < len(runs) - keep:
            remove_worktree(rid)
            shutil.rmtree(Path(root) / ".gruntly" / "runs" / rid, ignore_errors=True)
            removed.append(rid)
    wts = Path(root) / ".gruntly" / "worktrees"
    if wts.is_dir():
        for p in wts.iterdir():
            if not (Path(root) / ".gruntly" / "runs" / p.name).is_dir():
                remove_worktree(p.name)
                removed.append(p.name)
    states = Path(root) / ".gruntly" / "child-state"
    if states.is_dir():
        for p in states.iterdir():
            if not (Path(root) / ".gruntly" / "runs" / p.name).is_dir():
                force_rmtree(p)
                removed.append("child-state/" + p.name)
    return removed
