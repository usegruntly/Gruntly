"""Run shell commands (acceptance, lint, typecheck) in the worktree. Never trusts the child."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

MAX_CAPTURE = 200_000


def purge_bytecode(root: Path) -> None:
    """A stale .pyc (same size, same-second mtime) can hide an edit and make a correct fix look broken."""
    for dp, dn, _ in os.walk(root):
        dn[:] = [d for d in dn if d != ".git"]
        for d in list(dn):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dp, d), ignore_errors=True)
                dn.remove(d)


def run_cmd(cmd: str, cwd: Path, timeout_s: int, env: dict | None = None) -> dict:
    env = {**(env if env is not None else os.environ), "PYTHONDONTWRITEBYTECODE": "1"}
    purge_bytecode(cwd)
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True,
                           encoding="utf8", errors="replace", timeout=timeout_s, env=env)
        out = (p.stdout or "") + (p.stderr or "")
        ok, code = p.returncode == 0, p.returncode
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode("utf8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
        out += f"\n[gruntly] timed out after {timeout_s}s"
        ok, code = False, None
    return {"ok": ok, "cmd": cmd, "exit": code, "output": out[-MAX_CAPTURE:], "secs": round(time.monotonic() - t0, 1)}


def check(spec, wt: Path) -> dict:
    last = {"ok": True, "cmd": "", "exit": 0, "output": "", "secs": 0}
    total = 0.0
    for a in spec.acceptance:
        r = run_cmd(a["cmd"], wt, a["timeout_s"])
        total += r["secs"]
        last = r
        if not r["ok"]:
            break
    last["secs"] = round(total, 1)
    return last
