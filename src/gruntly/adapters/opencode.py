"""OpenCode (verified against 1.19.5, see docs/adapters.md)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import Caps, ChildOutcome, Command, Detection, count_malformed, kill_tree, which

PROVIDER = "lmstudio"


class OpenCodeAdapter:
    name = "opencode"

    def detect(self) -> Detection:
        exe = which("opencode")
        if not exe:
            return Detection(False, None, "opencode not on PATH (npm i -g opencode-ai)")
        try:
            v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception as e:  # noqa: BLE001
            return Detection(True, None, f"version check failed: {e}")
        return Detection(True, v)

    def command(self, task, workdir: Path, prompt: str, resume: str | None) -> Command:
        model = task.model or "default"
        cfg = {"$schema": "https://opencode.ai/config.json",
               "provider": {PROVIDER: {"npm": "@ai-sdk/openai-compatible", "name": "Local model",
                                       "options": {"baseURL": task.endpoint, "apiKey": task.api_key},
                                       "models": {model: {"name": model}}}}}
        # Private state dir per run: an old or foreign OpenCode database must not break (or leak into) runs.
        state = Path(workdir).parents[1] / "child-state" / Path(workdir).name / "opencode"
        argv = [which("opencode") or "opencode", "run", "--format", "json", "--auto", "-m", f"{PROVIDER}/{model}"]
        if resume:
            argv += ["-s", resume]
        env = {"OPENCODE_CONFIG_CONTENT": json.dumps(cfg), "XDG_DATA_HOME": str(state / "data"),
               "XDG_CONFIG_HOME": str(state / "config"), "XDG_STATE_HOME": str(state / "state"),
               "XDG_CACHE_HOME": str(state / "cache")}
        return Command(argv=argv, env=env, stdin=prompt)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome:
        events = []
        for line in stdout.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        out = ChildOutcome(malformed_calls=count_malformed(stderr, "" if events else stdout))
        if not events:
            out.is_error = True
            out.final_message = (stderr or stdout).strip()[-600:]
            return out
        texts = [e["part"].get("text", "").strip() for e in events if e.get("type") == "text"]
        out.final_message = next((t for t in reversed(texts) if t), "")
        out.session_id = next((e.get("sessionID") for e in events if e.get("sessionID")), None)
        toks = [e["part"].get("tokens") or {} for e in events if e.get("type") == "step_finish"]
        if toks:
            out.usage = {"available": True, "input_tokens": sum(t.get("input", 0) for t in toks),
                         "output_tokens": sum(t.get("output", 0) for t in toks),
                         "total_tokens": sum(t.get("total", 0) for t in toks)}
        out.is_error = exit_code != 0 or any(e.get("type") == "error" for e in events)
        return out

    def capabilities(self) -> Caps:
        return Caps(resume=True, structured_output=True, serve_mode=True)

    def cancel(self, proc) -> None:
        kill_tree(proc)
