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

from .. import nobrowser
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
    modes: tuple[str, ...] = MODES          # the modes it can run in (Aider cannot be a delegating parent)
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
    try:
        cmd = adapter.command(task, mode, model, provider, structured)
    except ValueError as e:                    # a launch that cannot be built (no key for the provider, no model): say why, do not raise
        return RunResult(ParentOutcome(str(e), True), 2, "", "", None)
    base = Path(cwd) if cwd else Path.cwd()
    for rel, text in cmd.files.items():
        p = Path(rel) if Path(rel).is_absolute() else base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text.replace("{gruntly_cwd}", base.resolve().as_posix()), encoding="utf8")      # a file may name the folder the parent is launched in
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}     # so cancel() reaches the whole tree
    full = {**os.environ, **nobrowser.env(), **cmd.env, **(env or {})}      # unattended: no tab may open for the parent either (see gruntly/nobrowser.py)
    if cwd:
        full["PWD"] = str(cwd)      # OpenCode takes its project folder from $PWD, not from the process's real directory: a caller whose own shell is elsewhere
                                    # (the benchmark runner, a script) would otherwise have it run, and edit, the wrong repository (seen live, 2026-11-13)
    try:
        proc = subprocess.Popen(cmd.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf8",
                                errors="replace", cwd=str(cwd) if cwd else None, env=full, **kw)
    except FileNotFoundError:
        return RunResult(ParentOutcome(f"{adapter.name} is not installed or not on PATH", True), 127, "", "", cmd)
    try:
        stdout, stderr = proc.communicate(cmd.stdin, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        adapter.cancel(proc)                   # a Windows .cmd shim leaves its node child running if only the shim is killed
        try:
            proc.communicate(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        return RunResult(ParentOutcome(f"{adapter.name} did not finish in {timeout_s} s", True), 124, "", "", cmd)
    return RunResult(adapter.parse(stdout or "", stderr or "", proc.returncode), proc.returncode, stdout or "", stderr or "", cmd)
