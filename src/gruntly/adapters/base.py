from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# Only these variables reach the child. Everything else (ANTHROPIC_*, OPENAI_*, cloud and
# GitHub tokens) is dropped; adapters add the local-endpoint variables explicitly.
BASE_ENV_KEYS = [
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "HOME", "USERPROFILE", "HOMEDRIVE",
    "HOMEPATH", "TEMP", "TMP", "TMPDIR", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "PROGRAMDATA", "USERNAME", "LANG", "LC_ALL", "TERM", "SHELL", "TZ",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
]
MALFORMED = re.compile(r"(?i)(invalid tool call|malformed tool|failed to parse tool|tool call.*(?:parse|json) error|"
                       r"unknown tool|invalid arguments? for tool)")


@dataclass
class Detection:
    installed: bool
    version: str | None = None
    detail: str = ""


@dataclass
class Command:
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    stdin: str | None = None


@dataclass
class ChildOutcome:
    final_message: str = ""
    session_id: str | None = None
    usage: dict = field(default_factory=lambda: {"available": False})
    is_error: bool = False
    malformed_calls: int = 0


@dataclass
class Caps:
    resume: bool = False
    structured_output: bool = False
    serve_mode: bool = False


class Adapter(Protocol):
    name: str

    def detect(self) -> Detection: ...
    def command(self, task, workdir: Path, prompt: str, resume: str | None) -> Command: ...
    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome: ...
    def capabilities(self) -> Caps: ...
    def cancel(self, proc: subprocess.Popen) -> None: ...


def scrub_env(extra: dict[str, str], allow: list[str] | None = None) -> dict[str, str]:
    keys = set(BASE_ENV_KEYS) | set(allow or [])
    base = {k: v for k, v in os.environ.items() if k.upper() in {x.upper() for x in keys}}
    return {**base, "PYTHONDONTWRITEBYTECODE": "1", **extra}


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill the child and everything it spawned."""
    if proc.poll() is not None and os.name != "nt":
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def which(name: str) -> str | None:
    return shutil.which(name)


def count_malformed(*texts: str) -> int:
    return sum(len(MALFORMED.findall(t)) for t in texts)


INSTALL_ORDER = ("opencode", "qwen", "hermes")   # opencode first: it is the one benchmarked and traced most


def pick_installed() -> str | None:
    """The first child harness found on this machine, or None."""
    for name in INSTALL_ORDER:
        if get_adapter(name).detect().installed:
            return name
    return None


def get_adapter(name: str, spec=None) -> "Adapter":
    from .aider import AiderAdapter
    from .claude import ClaudeAdapter
    from .codex import CodexAdapter
    from .gemini import GeminiAdapter
    from .generic import GenericAdapter
    from .hermes import HermesAdapter
    from .opencode import OpenCodeAdapter
    from .qwen import QwenAdapter

    table = {"claude": ClaudeAdapter, "generic": GenericAdapter, "qwen": QwenAdapter, "opencode": OpenCodeAdapter, "hermes": HermesAdapter,
             "codex": CodexAdapter, "gemini": GeminiAdapter, "aider": AiderAdapter}
    return table[name]()
