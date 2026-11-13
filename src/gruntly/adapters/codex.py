"""Codex CLI as a child (checked against 0.167.2, the real binary against a stub model server that speaks the Responses API).

Run as shipped (its own prompt and tools) with `codex exec --json`, the task on stdin. gruntly points it at the endpoint it gives every child
(the local server, or the rate-limit proxy of a hosted provider) as a custom provider with `wire_api = "responses"`, because that is the only
wire API Codex speaks: the endpoint has to serve `/v1/responses` (LM Studio and Ollama do; so do OpenAI, OpenRouter and a few other hosted
providers, see `responses_api` in `gruntly providers`). The key is passed in the environment (`env_key`), never in the command line. A private
`CODEX_HOME` per run keeps your own Codex login, config, rules and history out of it, and the parent's permission mode picks the sandbox.
A session is not resumed (a follow-up starts a fresh session on the same tree).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..spec import permission_mode
from .base import Caps, ChildOutcome, Command, Detection, count_malformed, kill_tree, which

PROVIDER = "gruntly"
KEY_ENV = "GRUNTLY_CHILD_API_KEY"


def toml_table(d: dict) -> str:
    """A TOML inline table; JSON strings are valid TOML basic strings."""
    return "{" + ", ".join(f"{k} = {json.dumps(v)}" for k, v in d.items()) + "}"


def parse_events(stdout: str) -> tuple[str, str | None, dict | None, str, int]:
    """(final message, session id, usage totals or None, failure text, turns) from `codex exec --json` events. An `error` item is only a
    warning (Codex says so when it has no metadata for a model it does not know); a `turn.failed` or top-level `error` event is a failure."""
    text, session, failure, turns = "", None, "", 0
    tot = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    for line in (stdout or "").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        t = e.get("type")
        if t == "thread.started":
            session = e.get("thread_id")
        elif t == "item.completed" and isinstance(e.get("item"), dict) and e["item"].get("type") == "agent_message":
            text = str(e["item"].get("text") or text)
        elif t == "turn.completed" and isinstance(e.get("usage"), dict):
            u = e["usage"]
            tot["input_tokens"] += int(u.get("input_tokens") or 0)
            tot["output_tokens"] += int(u.get("output_tokens") or 0)
            tot["cached_input_tokens"] += int(u.get("cached_input_tokens") or 0)
            turns += 1
        elif t in ("turn.failed", "error"):
            err = e.get("error")
            failure = str(e.get("message") or (err.get("message") if isinstance(err, dict) else err) or "the turn failed")
    return text.strip(), session, (tot if turns else None), failure, turns


class CodexAdapter:
    name = "codex"

    def detect(self) -> Detection:
        exe = which("codex")
        if not exe:
            return Detection(False, None, "codex not on PATH (npm i -g @openai/codex)")
        try:
            v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
        except Exception as e:  # noqa: BLE001
            return Detection(True, None, f"version check failed: {e}")
        return Detection(True, v.replace("codex-cli", "").strip() or None)

    def command(self, task, workdir: Path, prompt: str, resume: str | None) -> Command:
        model = task.model or "default"
        home = Path(workdir).parents[1] / "child-state" / Path(workdir).name / "codex-home"
        home.mkdir(parents=True, exist_ok=True)                 # Codex refuses a CODEX_HOME that does not exist
        entry = {"name": "gruntly", "base_url": task.endpoint, "env_key": KEY_ENV, "wire_api": "responses"}
        argv = [which("codex") or "codex", "exec", "--skip-git-repo-check", "--json", "--ephemeral", "-C", str(workdir),
                "-c", f"model_providers.{PROVIDER}={toml_table(entry)}", "-c", f'model_provider="{PROVIDER}"', "-m", model]
        mode = permission_mode(task)
        if mode == "bypass":
            argv += ["--dangerously-bypass-approvals-and-sandbox"]
        else:
            argv += ["-s", "read-only" if mode == "plan" else "workspace-write", "-c", 'approval_policy="never"']
        argv.append("-")                                     # the task on stdin
        return Command(argv=argv, env={"CODEX_HOME": str(home), KEY_ENV: task.api_key}, stdin=prompt)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome:
        text, session, tot, failure, turns = parse_events(stdout)
        out = ChildOutcome(malformed_calls=count_malformed(stderr, "" if text else stdout))
        if not text and not failure and not tot:
            out.is_error = True
            out.final_message = (stderr or stdout).strip()[-600:] or "no output"
            return out
        out.final_message = text or failure
        out.session_id = session
        out.is_error = bool(failure) or exit_code != 0
        if tot:
            out.usage = {"available": True, "input_tokens": tot["input_tokens"], "output_tokens": tot["output_tokens"],
                         "total_tokens": tot["input_tokens"] + tot["output_tokens"], "requests": turns,
                         "input_per_request": round(tot["input_tokens"] / turns) if turns else None}
        return out

    def capabilities(self) -> Caps:
        return Caps(resume=False, structured_output=True)

    def cancel(self, proc) -> None:
        kill_tree(proc)
