"""The parent side of a delegation: the harness that reads a task, calls gruntly and reports (delegating), or does the job itself (working).

This mirrors the child adapters (adapters/base.py), so any harness can sit on either side and any parent can be paired with any child.
A parent adapter knows how to build the launch (command line, environment, the task on stdin, any files to write first), how to read
what came back (final message, usage, cost), and what the harness can and cannot do of the lean delegating setup. When a harness
cannot do part of it (replace its system prompt, leave only a shell tool, allow only `gruntly` commands, switch off extensions) the
adapter says so in `ParentCaps`, degrades as far as it can, and records the limit in `ParentCommand.notes`: nothing is claimed that the
harness does not do.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..adapters.base import Detection, kill_tree, which  # noqa: F401  (re-exported for the adapters)
from ..usage import Usage

MODES = ("delegating", "working")


@dataclass
class ParentCaps:
    replace_system_prompt: bool = False     # the delegating prompt replaces the harness's own
    restrict_tools: bool = False            # only a shell tool is left in delegating mode
    restrict_shell: bool = False            # only `gruntly` commands run without asking
    disable_extensions: bool = False        # no MCP servers, skills, plugins or hooks
    reports_usage: bool = False             # tokens come back in its output
    reports_cost: bool = False              # a dollar figure comes back in its output
    non_interactive: bool = True            # can run headless with the task on stdin or the command line
    experimental: bool = False              # written from documentation, not yet checked live
    notes: tuple[str, ...] = ()


@dataclass
class ParentCommand:
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    stdin: str | None = None
    files: dict[str, str] = field(default_factory=dict)      # path -> text, written before launch (relative paths are under the working dir)
    notes: list[str] = field(default_factory=list)            # limits in effect for this launch (what could not be done, and what was done instead)


@dataclass
class ParentOutcome:
    final_message: str = ""
    is_error: bool = False
    session_id: str | None = None
    usage: Usage | None = None
    cost_usd: float | None = None           # as the harness reported it, never computed here
    turns: int | None = None


@dataclass
class RunResult:
    outcome: ParentOutcome
    returncode: int
    stdout: str
    stderr: str
    command: ParentCommand | None = None


class ParentAdapter(Protocol):
    name: str

    def detect(self) -> Detection: ...
    def command(self, task: str, mode: str, model: str | None = None, provider: str | None = None, structured: bool = False) -> ParentCommand: ...
    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParentOutcome: ...
    def capabilities(self) -> ParentCaps: ...
    def cancel(self, proc: subprocess.Popen) -> None: ...


def check_mode(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}, not {mode!r}")
    return mode


def run(adapter: ParentAdapter, task: str, mode: str, model: str | None = None, provider: str | None = None, cwd: Path | None = None,
        timeout_s: int = 900, structured: bool = False, env: dict | None = None) -> RunResult:
    """Launch a parent: write its files, give it the task on stdin, wait, read the result. A missing harness or a timeout is an error
    outcome with the reason in `final_message`, not an exception."""
    cmd = adapter.command(task, mode, model, provider, structured)
    base = Path(cwd) if cwd else Path.cwd()
    for rel, text in cmd.files.items():
        p = Path(rel) if Path(rel).is_absolute() else base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf8")
    try:
        p = subprocess.run(cmd.argv, input=cmd.stdin, text=True, encoding="utf8", errors="replace", capture_output=True,
                           cwd=str(cwd) if cwd else None, timeout=timeout_s, env={**os.environ, **cmd.env, **(env or {})})
    except FileNotFoundError:
        return RunResult(ParentOutcome(f"{adapter.name} is not installed or not on PATH", True), 127, "", "", cmd)
    except subprocess.TimeoutExpired:
        return RunResult(ParentOutcome(f"{adapter.name} did not finish in {timeout_s} s", True), 124, "", "", cmd)
    stdout, stderr = (p.stdout or ""), (getattr(p, "stderr", "") or "")
    return RunResult(adapter.parse(stdout, stderr, p.returncode), p.returncode, stdout, stderr, cmd)
