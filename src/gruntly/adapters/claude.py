"""Claude Code as the child (checked against 2.1.322): `claude -p` run inside the run's worktree, a cheaper model (Haiku by
default) doing the work a more expensive parent delegated.

Unlike the other children this one is paid: it runs in the person's own Claude usage, so the adapter reports the dollars the
CLI says it spent (`total_cost_usd`) and gruntly counts them.

The child is Claude Code as shipped (its own system prompt and every tool), with three differences that exist to stop it
calling gruntly again or loading the person's setup:
  - `--setting-sources project,local`: not the user's settings, so none of their plugins (gruntly itself), hooks or MCP servers;
  - `--strict-mcp-config` and `--disable-slash-commands`: no MCP, no skills;
  - `--disallowedTools Bash(gruntly *)`: even if one is loaded, it cannot delegate.
`--bare` is not used: it ends OAuth/keychain sign-in and would break everybody who logs in instead of using an API key.
The prompt goes on stdin (the Windows `.cmd` shim mangles multi-line arguments); output is stream-json so progress is visible.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from ..spec import permission_mode
from .base import Caps, ChildOutcome, Command, Detection, kill_tree, which

DEFAULT_MODEL = "haiku"
MAX_TURNS = 40
MAX_USD = 0.50            # per attempt; GRUNTLY_CLAUDE_CHILD_MAX_USD overrides. Checked between turns, so one big turn can pass it.
MODES = {"bypass": "bypassPermissions", "accept-edits": "acceptEdits", "plan": "plan"}


class ClaudeAdapter:
    name = "claude"

    def detect(self) -> Detection:
        exe = which("claude")
        if not exe:
            return Detection(False, None, "claude not on PATH (install Claude Code: https://docs.claude.com/en/docs/claude-code)")
        try:
            v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception as e:  # noqa: BLE001
            return Detection(True, None, f"version check failed: {e}")
        return Detection(True, v)

    def command(self, task, workdir: Path, prompt: str, resume: str | None) -> Command:
        exe = which("claude") or "claude"
        try:
            cap = float(os.environ.get("GRUNTLY_CLAUDE_CHILD_MAX_USD") or MAX_USD)
        except ValueError:
            cap = MAX_USD
        argv = [exe, "-p", "--model", task.model or DEFAULT_MODEL, "--output-format", "stream-json", "--verbose",
                "--permission-mode", MODES[permission_mode(task)],
                "--setting-sources", "project,local", "--strict-mcp-config", "--disable-slash-commands",
                "--disallowedTools", "Bash(gruntly *)",
                "--max-turns", str(MAX_TURNS), "--max-budget-usd", f"{cap:.2f}"]
        if resume:
            argv += ["--resume", resume]
        return Command(argv=argv, env={}, stdin=prompt)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome:
        res = None
        for line in (stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if isinstance(o, dict) and o.get("type") == "result":
                res = o
        out = ChildOutcome()
        if res is None:
            out.is_error = True
            out.final_message = ((stderr or "") or (stdout or "")).strip()[-600:]
            return out
        subtype = str(res.get("subtype") or "")
        out.final_message = str(res.get("result") or "").strip() or (subtype.replace("_", " ") if subtype.startswith("error") else "")
        out.session_id = res.get("session_id")
        out.is_error = bool(res.get("is_error")) or subtype.startswith("error") or exit_code != 0
        u = res.get("usage") or {}
        inp = sum(u.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        outp = u.get("output_tokens") or 0
        out.usage = {"available": True, "input_tokens": inp, "output_tokens": outp, "total_tokens": inp + outp,
                     "requests": res.get("num_turns"), "cost_usd": res.get("total_cost_usd")}
        return out

    def capabilities(self) -> Caps:
        return Caps(resume=True, structured_output=True)

    def cancel(self, proc) -> None:
        kill_tree(proc)
