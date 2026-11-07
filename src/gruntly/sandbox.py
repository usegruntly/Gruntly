"""Sandbox levels. Level 0 is NOT a security boundary: worktree + scrubbed env + checks afterwards.

Level 1 wraps the child in bubblewrap (Linux): the host is read-only, only the worktree (and the
main repo's .git, which worktrees need) is writable, and the network is off unless the model
endpoint is on the host (then the network namespace is shared).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from .adapters.base import Command, which


def level_available(level: int) -> tuple[bool, str]:
    if level == 0:
        return True, "level 0: worktree + scrubbed env (not a security boundary)"
    if level == 1:
        if not sys.platform.startswith("linux"):
            return False, "level 1 needs Linux (bubblewrap)"
        return (True, "bubblewrap found") if which("bwrap") else (False, "bwrap not installed")
    return False, "level 2 (container) is not built in v1"


def wrap(cmd: Command, level: int, workdir: Path, repo_root: Path, endpoint: str = "") -> Command:
    if level == 0:
        return cmd
    ok, why = level_available(level)
    if not ok:
        raise RuntimeError(f"sandbox level {level} unavailable: {why}")
    host = urlparse(endpoint).hostname or ""
    local_model = host in ("127.0.0.1", "localhost", "::1")
    args = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--bind", str(workdir), str(workdir), "--bind", str(repo_root / ".git"), str(repo_root / ".git"),
            "--chdir", str(workdir), "--die-with-parent", "--unshare-pid"]
    if not local_model:
        args.append("--unshare-net")
    home = os.path.expanduser("~")
    for sub in (".qwen", ".config/opencode", ".local/share/opencode", ".hermes"):
        p = os.path.join(home, sub)
        if os.path.isdir(p):
            args += ["--bind", p, p]
    return Command(argv=args + ["--", *cmd.argv], env=cmd.env, stdin=cmd.stdin)
