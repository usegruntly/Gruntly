"""Hermes Agent (Nous Research, `pip install hermes-agent`; verified against 0.19.0, live, on Linux/WSL2 with a hosted endpoint).

Hermes runs on Linux, macOS and WSL2 (the Windows install fails to build `pywinpty`), so on Windows run gruntly inside WSL2 too:
then Hermes, gruntly and gruntly's local rate-limit proxy all share one loopback.

How a run is wired:
  * Hermes reads its model endpoint from `$HERMES_HOME/config.yaml`. gruntly keeps one home per project
    (`.gruntly/child-state/hermes-home`, so sessions and Hermes's model-metadata cache survive between attempts) and rewrites its
    `custom_providers` and `model` entries before every attempt, because the endpoint (the proxy's port) changes per run.
  * `chat -Q -q PROMPT` is the headless mode: the final answer on stdout, `session_id: ID` on stderr. `--resume ID` continues it.
  * `--ignore-rules` keeps Hermes from injecting AGENTS.md / SOUL.md / memory: the task prompt is all it gets from gruntly.
  * The permission mode follows the parent: bypass passes `--yolo`; accept-edits and plan give it only the `file` toolset
    (read, search, patch, write), so there is no shell. Hermes cannot make edits read-only, so plan is the same as accept-edits.

Known limits: quiet mode prints no tool trace (the live view and the trace line are empty for Hermes), no token usage is
reported, and every request carries Hermes's own system prompt and tool list (about 18 tools).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from ..spec import permission_mode
from .base import Caps, ChildOutcome, Command, Detection, count_malformed, kill_tree, which

PROVIDER = "gruntly"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SESSION = re.compile(r"^\s*session_id:\s*(\S+)\s*$", re.M)
UTF8 = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONIOENCODING": "utf-8"}   # an ASCII locale makes Hermes strip non-ASCII text


def home_for(workdir: Path) -> Path:
    """Hermes' data folder. One per project by default. GRUNTLY_HERMES_HOME names a single shared folder instead: newer Hermes
    builds prepare their own dependency environment for each data folder (slow, and it fails on Windows paths over 260
    characters), so prepare one short-path folder once (`hermes pm repair`) and point every project at it."""
    shared = os.environ.get("GRUNTLY_HERMES_HOME")
    return Path(shared) if shared else Path(workdir).parents[1] / "child-state" / "hermes-home"


def write_config(home: Path, endpoint: str, api_key: str, model: str) -> Path:
    """Point Hermes at an OpenAI-compatible endpoint. JSON strings are valid YAML scalars, so values need no quoting rules."""
    home.mkdir(parents=True, exist_ok=True)
    text = (
        "custom_providers:\n"
        f"  - name: {PROVIDER}\n"
        f"    base_url: {json.dumps(endpoint)}\n"
        f"    api_key: {json.dumps(api_key)}\n"
        f"    model: {json.dumps(model)}\n"
        "model:\n"
        f"  provider: custom:{PROVIDER}\n"
        f"  default: {json.dumps(model)}\n"
    )
    p = home / "config.yaml"
    p.write_text(text, encoding="utf8", newline="\n")
    return p


def find_hermes() -> str | None:
    """`hermes` on PATH, else where the Windows installer puts it (%LOCALAPPDATA%/hermes/bin): that folder is not always on the PATH
    a tool's own shell sees, for example the one Claude Code runs commands in."""
    exe = which("hermes")
    if exe:
        return exe
    base = os.environ.get("LOCALAPPDATA")
    if base:
        cand = Path(base) / "hermes" / "bin" / "hermes.exe"
        if cand.is_file():
            return str(cand)
    return None


class HermesAdapter:
    name = "hermes"

    def detect(self) -> Detection:
        exe = find_hermes()
        if not exe:
            return Detection(False, None, "hermes not found (`uv tool install hermes-agent` on Linux, macOS or WSL2; "
                                          "on Windows the Hermes installer, which puts it in %LOCALAPPDATA%/hermes/bin)")
        try:
            out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout
            m = re.search(r"v?(\d+\.\d+\.\d+)", out)
            return Detection(True, m.group(1) if m else None)
        except Exception as e:  # noqa: BLE001
            return Detection(True, None, f"version check failed: {e}")

    def command(self, task, workdir: Path, prompt: str, resume: str | None) -> Command:
        model = task.model or "default"
        home = home_for(workdir)
        write_config(home, task.endpoint, task.api_key, model)
        mode = permission_mode(task)
        argv = [find_hermes() or "hermes", "chat", "-Q", "--ignore-rules", "--provider", f"custom:{PROVIDER}", "-m", model]
        argv += ["--yolo"] if mode == "bypass" else ["-t", "file"]
        if resume:
            argv += ["--resume", resume]
        argv += ["-q", prompt]
        return Command(argv=argv, env={"HERMES_HOME": str(home), **UTF8}, stdin=None)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome:
        out, err = ANSI.sub("", stdout or ""), ANSI.sub("", stderr or "")
        m = SESSION.search(err) or SESSION.search(out)
        lines = [ln for ln in out.splitlines()
                 if ln.strip() and not ln.lstrip().startswith(("┊", "⚠", "tirith"))]   # tool previews and warnings are not the answer
        message = "\n".join(lines).strip()
        return ChildOutcome(final_message=message[-2000:], session_id=m.group(1) if m else None,
                            is_error=exit_code != 0, malformed_calls=count_malformed(out, err))

    def capabilities(self) -> Caps:
        return Caps(resume=True)

    def cancel(self, proc) -> None:
        kill_tree(proc)
