"""OpenCode as a parent (checked against 1.19.5 with `opencode debug agent` and against the real binary talking to a stub model server, see
gruntly/probe.py: no key, no cost).

**Delegating** defines one primary agent, `gruntly`, in the config OpenCode reads from `OPENCODE_CONFIG_CONTENT`: its prompt is the delegating
prompt, every tool is denied except `bash`, and bash is denied except `gruntly *`. Measured against the real binary: the system prompt went
from about 21,800 characters to about 1,900 (ours plus a few lines of environment), the tools offered from ten to `bash`. `--pure` leaves
external plugins out. **Working** is OpenCode's own default agent with every tool, auto-approved.

Limits, said in `ParentCommand.notes` and the capability record: OpenCode makes one extra small request per session to title it; MCP servers in
your own config still start (their tools are denied); `AGENTS.md` in the project is still read. Your own login and default model are used unless
a provider is named; a catalog provider (OpenRouter, NVIDIA, ...) is added as an OpenAI-compatible provider, its key passed in the environment.
"""
from __future__ import annotations

import json
import subprocess

from .. import providers
from ..adapters.opencode import OpenCodeAdapter
from ..usage import Usage
from . import prompts
from .base import Detection, ParentCaps, ParentCommand, ParentOutcome, check_mode, kill_tree, which

DENY = "deny"
STEPS = 16                       # agentic iterations before OpenCode forces a text-only answer: a delegating parent needs a handful
AGENT = "gruntly"


def lean_config() -> dict:
    """The delegating agent: our prompt, no tool but bash, and bash only for gruntly commands. `*` first so a tool nobody named (an MCP
    server's, a plugin's) is denied too."""
    perm = {"*": DENY, "read": DENY, "edit": DENY, "glob": DENY, "grep": DENY, "list": DENY, "task": DENY, "webfetch": DENY, "websearch": DENY,
            "todowrite": DENY, "skill": DENY, "lsp": DENY, "question": DENY, "external_directory": DENY, "bash": {"*": DENY, "gruntly *": "allow"}}
    return {"default_agent": AGENT,
            "agent": {AGENT: {"mode": "primary", "description": "Directs gruntly", "prompt": prompts.DELEGATING, "steps": STEPS, "permission": perm}}}


def provider_setup(provider: str | None, model: str | None) -> tuple[str | None, dict, dict[str, str]]:
    """(the -m value, the config's provider block, environment to add) for a catalog provider. No provider: the harness's own login and
    default, and `model` is passed as OpenCode writes it (`provider/model`)."""
    if not provider:
        return model, {}, {}
    p = providers.ALL.get(provider)
    if p is None:
        raise ValueError(f"unknown provider {provider!r}; known: {', '.join(providers.ALL)}")
    env: dict[str, str] = {}
    key_expr = "local"
    if p.kind != "local":
        key = providers.api_key(p)
        if not key:
            raise ValueError(f"no API key for {p.name}: run `gruntly auth set {p.name}` (or set {p.key_env})")
        env[p.key_env] = key                                           # in the environment, never on the command line or in the config text
        key_expr = "{env:" + p.key_env + "}"
    use = model or p.default_model
    if not use:
        raise ValueError(f"provider {p.name} has no default model: pass --model ID (see `gruntly models {p.name}`)")
    pid = f"gruntly-{p.name}"
    block = {pid: {"npm": "@ai-sdk/openai-compatible", "name": p.name, "options": {"baseURL": p.base_url, "apiKey": key_expr},
                   "models": {use: {"name": use}}}}
    return f"{pid}/{use}", block, env


class OpenCodeParent:
    name = "opencode"

    def detect(self) -> Detection:
        exe = which("opencode")
        if not exe:
            return Detection(False, None, "opencode not on PATH (install OpenCode: https://opencode.ai)")
        try:
            v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception as e:  # noqa: BLE001
            return Detection(True, None, f"version check failed: {e}")
        return Detection(True, v)

    def command(self, task: str, mode: str, model: str | None = None, provider: str | None = None, structured: bool = False) -> ParentCommand:
        check_mode(mode)
        m_arg, block, env = provider_setup(provider, model)
        cfg: dict = {"$schema": "https://opencode.ai/config.json"}
        if block:
            cfg["provider"] = block
        argv = [which("opencode") or "opencode", "run", "--format", "json", "--auto"]
        notes: list[str] = []
        if mode == "delegating":
            cfg.update(lean_config())
            argv.append("--pure")
            notes += ["OpenCode makes one extra small request per session to title it", "MCP servers in your own OpenCode config still start (their tools are denied)",
                      "AGENTS.md in the project is still read by OpenCode"]
        if m_arg:
            argv += ["-m", m_arg]
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg)
        return ParentCommand(argv=argv, env=env, stdin=task, notes=notes)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParentOutcome:
        c = OpenCodeAdapter().parse(stdout, stderr, exit_code)
        u = c.usage if c.usage.get("available") else None
        usage = Usage(prompt=u.get("input_tokens") or 0, completion=u.get("output_tokens") or 0, requests=u.get("requests") or 0) if u else None
        return ParentOutcome(final_message=c.final_message, is_error=c.is_error, session_id=c.session_id, usage=usage, turns=(u or {}).get("requests"))

    def capabilities(self) -> ParentCaps:
        return ParentCaps(replace_system_prompt=True, restrict_tools=True, restrict_shell=True, disable_extensions=True, reports_usage=True,
                          reports_cost=False, notes=("one extra title request per session", "MCP servers in your config still start", "AGENTS.md is still read"))

    def cancel(self, proc) -> None:
        kill_tree(proc)
