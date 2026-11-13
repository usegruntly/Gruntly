"""Gemini CLI as a child (checked against 0.68.0, the real binary through gruntly's bridge to a stub OpenAI-compatible server).

Gemini CLI speaks only the Gemini API, and a child is handed an OpenAI-compatible endpoint (a local model server, or gruntly's rate-limit proxy in front of
a hosted provider). So the runner starts a bridge (`gruntly/geminibridge.py`) for a Gemini child: a small local server that takes the CLI's Gemini requests,
turns each into one chat completion for that endpoint, and turns the answer back, tool calls included. The CLI is pointed at it with
`GOOGLE_GEMINI_BASE_URL`; the key it sends is a placeholder, the real one (if any) stays in the proxy.

Run as shipped (its own prompt of about 30,400 characters and 15 tools) with `gemini -p " " -o json`, the task on stdin; a private `GEMINI_CLI_HOME` per run
keeps your own login, settings, extensions and history out of it. The parent's permission mode picks the approval mode (bypass: yolo, accept-edits:
auto_edit, plan: plan). Output is one JSON object: the reply, the session id, and per-model token counts. A session is not resumed.

Limits: the bridge sends the model the server's own sampling settings, not the CLI's (temperature 1, top-p 0.95, top-k 64 are Gemini defaults); streaming is
not used (the answer arrives whole); a model that does not support tool calls cannot drive this harness; the CLI's large prompt and tool list want a
context of 32k or more.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..spec import permission_mode
from .base import Caps, ChildOutcome, Command, Detection, count_malformed, kill_tree, which

MODES = {"bypass": "yolo", "accept-edits": "auto_edit", "plan": "plan"}
SETTINGS = {"security": {"auth": {"selectedType": "gemini-api-key"}}}
needs_bridge = True                      # the runner starts a Gemini-protocol bridge in front of the child endpoint (see runner._execute_inner)


def parse_json(stdout: str) -> dict | None:
    """The JSON object `gemini -o json` prints (log lines may come before it), or None."""
    s = (stdout or "").strip()
    for cand in (s, s[s.find("{"):] if "{" in s else ""):
        try:
            d = json.loads(cand)
        except ValueError:
            continue
        if isinstance(d, dict):
            return d
    return None


def totals(data: dict) -> dict | None:
    """Token totals over the models in the stats block: prompt (cached included), candidates, cached, thoughts, requests; None when there are none."""
    models = (data.get("stats") or {}).get("models") or {}
    tot = {"prompt": 0, "completion": 0, "cached": 0, "reasoning": 0, "requests": 0}
    for m in models.values():
        t, a = m.get("tokens") or {}, m.get("api") or {}
        tot["prompt"] += int(t.get("prompt") or t.get("input") or 0)
        tot["completion"] += int(t.get("candidates") or 0)
        tot["cached"] += int(t.get("cached") or 0)
        tot["reasoning"] += int(t.get("thoughts") or 0)
        tot["requests"] += int(a.get("totalRequests") or 0)
    return tot if tot["requests"] else None


class GeminiAdapter:
    name = "gemini"
    needs_bridge = True

    def detect(self) -> Detection:
        exe = which("gemini")
        if not exe:
            return Detection(False, None, "gemini not on PATH (npm i -g @google/gemini-cli)")
        try:
            v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
        except Exception as e:  # noqa: BLE001
            return Detection(True, None, f"version check failed: {e}")
        return Detection(True, v.splitlines()[-1].strip() if v else None)

    def command(self, task, workdir: Path, prompt: str, resume: str | None) -> Command:
        bridge = getattr(task, "_bridge_url", None)
        if not bridge:
            raise RuntimeError("the Gemini CLI child needs the bridge to the endpoint, which the runner starts; it was not started")
        model = task.model or "default"
        home = Path(workdir).parents[1] / "child-state" / Path(workdir).name / "gemini-home"
        (home / ".gemini").mkdir(parents=True, exist_ok=True)
        (home / ".gemini" / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf8")
        argv = [which("gemini") or "gemini", "-m", model, "--skip-trust", "--approval-mode", MODES[permission_mode(task)], "-o", "json", "-p", " "]
        env = {"GEMINI_CLI_HOME": str(home), "GEMINI_API_KEY": "gruntly-bridge", "GOOGLE_GEMINI_BASE_URL": bridge}
        return Command(argv=argv, env=env, stdin=prompt)               # the task on stdin: the npm .cmd shim mangles multi-line arguments

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome:
        data = parse_json(stdout)
        out = ChildOutcome(malformed_calls=count_malformed(stderr, "" if data else stdout))
        if data is None:
            out.is_error = True
            out.final_message = (stderr or stdout).strip()[-600:] or "no output"
            return out
        out.session_id = data.get("session_id")
        err = data.get("error")
        if err:
            out.is_error = True
            out.final_message = str(err.get("message") if isinstance(err, dict) else err)
            return out
        out.final_message = str(data.get("response") or "").strip()
        out.is_error = exit_code != 0
        t = totals(data)
        if t:
            out.usage = {"available": True, "input_tokens": t["prompt"], "output_tokens": t["completion"], "total_tokens": t["prompt"] + t["completion"],
                         "requests": t["requests"], "input_per_request": round(t["prompt"] / t["requests"])}
        return out

    def capabilities(self) -> Caps:
        return Caps(resume=False, structured_output=True)

    def cancel(self, proc) -> None:
        kill_tree(proc)
