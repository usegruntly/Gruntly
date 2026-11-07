"""Qwen Code (verified against 0.26.9, see docs/adapters.md).

Slim profiles use `--bare`: it skips auto-discovery (settings, hooks, MCP, skills, memory) and turns off the
managed-memory extractor, a separate ~7k-token request on every run. Bare mode forces the core tools to
read_file, edit, notebook_edit and run_shell_command (`--core-tools` is ignored), so the profile removes the ones
it does not want with `--exclude-tools`. There is no whole-file write tool in bare mode; `edit` creates files
when `old_string` is empty. `--system-prompt` replaces the default system prompt.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import Caps, ChildOutcome, Command, Detection, count_malformed, kill_tree, which

SYSTEM = "You change code files in the current directory using the tools provided. Be concise."
BARE_TOOLS = {"read": ["read_file"], "write": ["edit"], "edit": ["edit"], "test": ["run_shell_command"]}
BARE_ALL = ["read_file", "edit", "notebook_edit", "run_shell_command"]


class QwenAdapter:
    name = "qwen"

    def detect(self) -> Detection:
        exe = which("qwen")
        if not exe:
            return Detection(False, None, "qwen not on PATH (npm i -g @qwen-code/qwen-code)")
        try:
            v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception as e:  # noqa: BLE001
            return Detection(True, None, f"version check failed: {e}")
        return Detection(True, v)

    def command(self, task, workdir: Path, prompt: str, resume: str | None, profile=None) -> Command:
        exe = which("qwen") or "qwen"
        argv = [exe, "--auth-type", "openai", "--approval-mode", "yolo", "-o", "json",
                "--max-wall-time", str(max(30, int(task.budget_s)))]
        if profile is not None and profile.name != "default":
            keep = {t for logical in profile.tools for t in BARE_TOOLS.get(logical, [])}
            argv += ["--bare", "--system-prompt", SYSTEM]
            for t in BARE_ALL:
                if t not in keep:
                    argv += ["--exclude-tools", t]
        if task.model:
            argv += ["-m", task.model]
        if resume:
            argv += ["-r", resume]
        env = {"OPENAI_BASE_URL": task.endpoint, "OPENAI_API_KEY": task.api_key,
               "QWEN_CODE_SUPPRESS_YOLO_WARNING": "1"}
        # The prompt goes on stdin: the npm .cmd shim on Windows mangles multi-line arguments.
        return Command(argv=argv, env=env, stdin=prompt)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome:
        events = _events(stdout)
        res = next((e for e in reversed(events) if isinstance(e, dict) and e.get("type") == "result"), None)
        out = ChildOutcome(malformed_calls=count_malformed(stdout if not events else "", stderr))
        if res is None:
            out.is_error = True
            out.final_message = (stderr or stdout).strip()[-600:]
            return out
        out.final_message = str(res.get("result") or "").strip()
        out.session_id = res.get("session_id")
        out.is_error = bool(res.get("is_error")) or exit_code != 0
        u = res.get("usage") or {}
        if u:
            out.usage = {"available": True, "input_tokens": u.get("input_tokens"),
                         "output_tokens": u.get("output_tokens"), "total_tokens": u.get("total_tokens")}
            reqs = sum(((m.get("api") or {}).get("totalRequests") or 0)
                       for m in ((res.get("stats") or {}).get("models") or {}).values())
            if reqs and u.get("input_tokens"):
                out.usage.update(requests=reqs, input_per_request=round(u["input_tokens"] / reqs))
        return out

    def capabilities(self) -> Caps:
        return Caps(resume=True, structured_output=True, profiles=True)

    def cancel(self, proc) -> None:
        kill_tree(proc)


def _events(stdout: str) -> list:
    s = stdout.strip()
    if not s:
        return []
    for cand in (s, s[s.find("["):] if "[" in s else ""):
        try:
            data = json.loads(cand)
            return data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            continue
    events = []
    for line in s.splitlines():  # stream-json fallback
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events
