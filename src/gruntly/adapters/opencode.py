"""OpenCode (verified against 1.19.5, see docs/adapters.md).

Slim profiles (typist, worker) run a custom agent instead of OpenCode's default one. Measured: the default agent
sends ~10.8k input tokens on the first request of a trivial task; the slim agent sends ~1.1k. What makes the
difference: a one-line agent prompt (a custom `prompt` replaces the default system prompt), only the tools the
profile needs (each enabled tool's schema is sent on every request), and no AGENTS.md, ~/.claude skills or
plugin discovery.

Quirk: OpenCode puts edit, write and patch behind one `edit` permission, so `write` cannot be offered without
`edit`. The prompt asks for whole-file rewrites; the edit tool stays available.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import Caps, ChildOutcome, Command, Detection, count_malformed, kill_tree, which

PROVIDER = "lmstudio"
AGENT = "gruntly"
SYSTEM = "You change code files in the current directory using the tools provided. Be concise."
ALL_TOOLS = ["bash", "read", "write", "edit", "glob", "grep", "list", "patch", "webfetch", "websearch",
             "todowrite", "todoread", "task", "skill", "lsp", "question"]
# logical tool (profiles.py) -> OpenCode tools
TOOLMAP = {"read": ["read"], "write": ["write", "edit"], "edit": ["edit", "write"], "list": ["list"],
           "search": ["grep", "glob"], "test": ["bash"]}
SLIM_ENV = {"OPENCODE_DISABLE_PROJECT_CONFIG": "1", "OPENCODE_DISABLE_CLAUDE_CODE": "1",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1"}


def agent_config(task, profile) -> dict:
    on = {t for logical in profile.tools for t in TOOLMAP.get(logical, [])}
    cfg = {"mode": "primary", "description": "gruntly child", "prompt": SYSTEM,
           "tools": {t: (t in on) for t in ALL_TOOLS}}
    # A tool is only offered to the model if its permission is granted explicitly: with the tools map alone the
    # model received no tools at all (355 input tokens) and pasted its code into the reply instead of writing it.
    perm: dict = {}
    if on & {"edit", "write"}:
        perm["edit"] = "allow"
    for t in ("read", "list", "grep", "glob"):
        if t in on:
            perm[t] = "allow"
    if "bash" in on:  # only the acceptance command(s); rules are ordered and the last match wins
        rules = {"*": "deny"}
        rules.update({a["cmd"]: "allow" for a in task.acceptance})
        perm["bash"] = rules
    if perm:
        cfg["permission"] = perm
    return cfg


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

    def command(self, task, workdir: Path, prompt: str, resume: str | None, profile=None) -> Command:
        model = task.model or "default"
        cfg = {"$schema": "https://opencode.ai/config.json",
               "provider": {PROVIDER: {"npm": "@ai-sdk/openai-compatible", "name": "Local model",
                                       "options": {"baseURL": task.endpoint, "apiKey": task.api_key},
                                       "models": {model: {"name": model}}}}}
        # Private state dir per run: an old or foreign OpenCode database must not break (or leak into) runs.
        state = Path(workdir).parents[1] / "child-state" / Path(workdir).name / "opencode"
        argv = [which("opencode") or "opencode", "run", "--format", "json", "--auto", "-m", f"{PROVIDER}/{model}"]
        env = {"XDG_DATA_HOME": str(state / "data"), "XDG_CONFIG_HOME": str(state / "config"),
               "XDG_STATE_HOME": str(state / "state"), "XDG_CACHE_HOME": str(state / "cache")}
        if profile is not None and profile.name != "default":
            cfg["agent"] = {AGENT: agent_config(task, profile)}
            argv += ["--agent", AGENT, "--title", "gruntly"]
            env.update(SLIM_ENV)
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg)
        if resume:
            argv += ["-s", resume]
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
            inp = sum(t.get("input", 0) for t in toks)
            out.usage = {"available": True, "input_tokens": inp,
                         "output_tokens": sum(t.get("output", 0) for t in toks),
                         "total_tokens": sum(t.get("total", 0) for t in toks),
                         "requests": len(toks), "input_per_request": round(inp / len(toks))}
        out.is_error = exit_code != 0 or any(e.get("type") == "error" for e in events)
        return out

    def capabilities(self) -> Caps:
        return Caps(resume=True, structured_output=True, serve_mode=True, profiles=True, whole_file_write=True)

    def cancel(self, proc) -> None:
        kill_tree(proc)
