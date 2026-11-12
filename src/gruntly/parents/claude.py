"""Claude Code as a parent (checked against 2.1.322).

**Delegating** is the lean setup the benchmarks measured: `claude -p` with its system prompt replaced by the delegating prompt, one tool
(Bash), only `gruntly` commands allowed without asking, no MCP servers, no slash commands or skills. **Working** is Claude Code as
shipped (its own system prompt, every tool) with the edit tools allowed without asking, because a headless session that cannot edit
cannot do the job; it is also what an escalation runs.

`--bare` is not used: it ends OAuth sign-in and would break everybody who logs in instead of using an API key.
"""
from __future__ import annotations

import json
import subprocess

from ..usage import Usage, parse_usage
from . import prompts
from .base import Detection, ParentCaps, ParentCommand, ParentOutcome, check_mode, kill_tree, which

DEFAULT_MODEL = "sonnet"
FULL_TOOLS = "Bash,Read,Edit,Write,Glob,Grep"      # what a working session may use without asking: it has to be able to do the work
# A run can take minutes. If the Bash call ends first, the detached worker dies with it, so the call must outlive the run.
BASH_ENV = {"BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "600000"}


class ClaudeParent:
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

    def command(self, task: str, mode: str, model: str | None = None, provider: str | None = None, structured: bool = False) -> ParentCommand:
        check_mode(mode)
        exe = which("claude") or "claude"
        argv = [exe, "-p", "--model", model or DEFAULT_MODEL, "--output-format", "stream-json" if structured else "text"]
        if structured:
            argv.append("--verbose")                  # stream-json needs it
        notes: list[str] = []
        if provider not in (None, "anthropic"):
            notes.append(f"Claude Code talks to Anthropic only: provider {provider!r} is ignored for this parent")
        if mode == "delegating":
            argv += ["--system-prompt", prompts.DELEGATING, "--tools", "Bash", "--allowedTools", "Bash(gruntly *)",
                     "--strict-mcp-config", "--disable-slash-commands"]
        else:
            argv += ["--allowedTools", FULL_TOOLS]
        return ParentCommand(argv=argv, env=dict(BASH_ENV), stdin=task, notes=notes)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParentOutcome:
        res = None
        for line in (stdout or "").splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if isinstance(o, dict) and o.get("type") == "result":
                    res = o
        if res is None:                                 # text output: the reply is the whole of stdout
            return ParentOutcome(final_message=(stdout or "").strip(), is_error=exit_code != 0)
        subtype = str(res.get("subtype") or "")
        u: Usage | None = parse_usage({"usage": res.get("usage")}) if isinstance(res.get("usage"), dict) else None
        if u is not None:
            u.requests = 1
        return ParentOutcome(final_message=str(res.get("result") or "").strip(), session_id=res.get("session_id"),
                             is_error=bool(res.get("is_error")) or subtype.startswith("error") or exit_code != 0,
                             usage=u, cost_usd=res.get("total_cost_usd"), turns=res.get("num_turns"))

    def capabilities(self) -> ParentCaps:
        return ParentCaps(replace_system_prompt=True, restrict_tools=True, restrict_shell=True, disable_extensions=True,
                          reports_usage=True, reports_cost=True)

    def cancel(self, proc) -> None:
        kill_tree(proc)
