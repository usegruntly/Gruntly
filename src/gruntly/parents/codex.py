"""Codex CLI as a parent (checked against 0.167.2, the real binary talking to a stub model server that speaks the Responses API, see
gruntly/probe.py: no key, no cost).

**Delegating** runs from a private `CODEX_HOME` (gruntly's state folder, one per mode) that holds two files gruntly writes before launch:
`instructions.md`, our prompt, named by `model_instructions_file`, and `rules/default.rules`, one execution-policy rule that allows commands
starting with `gruntly`. The rest is flags: the sandbox read-only and approvals `never`, so a command no rule allows is refused
("blocked by policy": `cat`, a redirect, a chained command, all measured), while the allowed `gruntly` command runs outside the sandbox (a
stand-in `gruntly` wrote a file outside the workspace) and can create its worktrees. Features that add tools or prompt text are off
(multi_agent, goals, apps, plugins, hooks, image generation, browser and computer use), web search is disabled, the permission,
environment and collaboration-mode texts, bundled skills and project docs (AGENTS.md) are left out. Measured: nine tools and 19,500
characters of instructions by default; four tools and exactly our 1,548 characters here. The two tools that remain besides the shell
(`request_user_input`, `view_image`) have no switch in this version.
**Working** is Codex as shipped, with the workspace-write sandbox and no approval prompts.

Codex only speaks the Responses API (`wire_api = "chat"` is refused), and most providers serve only chat completions. A provider the catalog marks as serving
the Responses API (`responses_api`, from documentation) is used directly; every other one goes through gruntly's bridge (`gruntly/responsesbridge.py`): the launch
runs `python -m gruntly.responsesbridge --upstream URL -- codex ...`, which starts a small local server, puts its address in Codex's provider config and translates
Codex's requests and the model's answers, tool calls included. The key reaches Codex (`env_key`) and the bridge through the environment. Delegating needs a provider: its
private `CODEX_HOME` holds none of your ChatGPT login. Codex warns that it has no metadata for a model it does not know; the warning is cosmetic.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .. import providers
from ..adapters.codex import parse_events
from ..store import state_dir
from ..usage import Usage
from . import prompts
from .base import Detection, ParentCaps, ParentCommand, ParentOutcome, check_mode, kill_tree, which

FEATURES_OFF = ("multi_agent", "goals", "apps", "plugins", "hooks", "image_generation", "browser_use", "computer_use", "in_app_browser")
LEAN_CONFIG = ('web_search="disabled"', "include_permissions_instructions=false", "include_apps_instructions=false",
               "include_collaboration_mode_instructions=false", "include_environment_context=false", "project_doc_max_bytes=0",
               "skills.bundled.enabled=false", 'approval_policy="never"')
RULES = 'prefix_rule(pattern = ["gruntly"], decision = "allow")\n'
NOTES = ("two tools besides the shell stay (request_user_input, view_image): this version has no switch for them",
         "Codex warns that it has no metadata for a model it does not know; the warning is cosmetic")


def parent_home(mode: str = "delegating") -> Path:
    """The private CODEX_HOME for the parent (`GRUNTLY_CODEX_PARENT_HOME` names a base folder; otherwise under gruntly's state folder)."""
    shared = os.environ.get("GRUNTLY_CODEX_PARENT_HOME")
    return (Path(shared) if shared else state_dir() / "codex-parent") / mode


def _toml_table(d: dict) -> str:
    """A TOML inline table; JSON strings are valid TOML basic strings."""
    return "{" + ", ".join(f"{k} = {json.dumps(v)}" for k, v in d.items()) + "}"


BRIDGE_URL = "{bridge_url}"             # the wrapper (gruntly.responsesbridge) puts the bridge's address here


def bridged(p) -> bool:
    """Codex speaks only the Responses API. A provider the catalog marks as serving it is used directly; any other (chat only, or not known) goes through
    gruntly's Responses-to-chat bridge, which works with every provider that serves chat completions."""
    return p.responses_api is not True


def provider_setup(provider: str | None, model: str | None) -> tuple[list[str], str | None, dict[str, str], list[str], tuple[str, str] | None]:
    """(the `-c`/`-m` flags, the model, environment to add, notes, the bridge as (upstream URL, key variable) or None) for a catalog provider.
    No provider: Codex's own login and default."""
    if not provider:
        return (["-m", model] if model else []), model, {}, [], None
    p = providers.ALL.get(provider)
    if p is None:
        raise ValueError(f"unknown provider {provider!r}; known: {', '.join(providers.ALL)}")
    via = bridged(p)
    notes = [f"{p.name} does not serve the Responses API that Codex needs: gruntly translates Codex's requests to {p.name}'s chat API locally (a bridge)"] if via else []
    env: dict[str, str] = {}
    entry = {"name": p.name, "base_url": BRIDGE_URL if via else p.base_url, "wire_api": "responses"}
    if p.kind != "local":
        key = providers.api_key(p)
        if not key:
            raise ValueError(f"no API key for {p.name}: run `gruntly auth set {p.name}` (or set {p.key_env})")
        env[p.key_env] = key                                          # in the environment, never on the command line
        entry["env_key"] = p.key_env
    use = model or p.default_model
    if not use:
        raise ValueError(f"provider {p.name} has no default model: pass --model ID (see `gruntly models {p.name}`)")
    pid = f"gruntly_{p.name}"
    flags = ["-c", f"model_providers.{pid}={_toml_table(entry)}", "-c", f"model_provider={json.dumps(pid)}", "-m", use]
    return flags, use, env, notes, ((p.base_url, p.key_env if p.kind != "local" else "") if via else None)


class CodexParent:
    name = "codex"

    def detect(self) -> Detection:
        exe = which("codex")
        if not exe:
            return Detection(False, None, "codex not on PATH (npm i -g @openai/codex)")
        try:
            out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
        except Exception as e:  # noqa: BLE001
            return Detection(True, None, f"version check failed: {e}")
        return Detection(True, out.replace("codex-cli", "").strip() or None)

    def command(self, task: str, mode: str, model: str | None = None, provider: str | None = None, structured: bool = False) -> ParentCommand:
        check_mode(mode)
        flags, _use, env, notes, bridge = provider_setup(provider, model)
        argv = [which("codex") or "codex", "exec", "--skip-git-repo-check", "--json", *flags]
        files: dict[str, str] = {}
        if mode == "delegating":
            if not provider:
                raise ValueError("Codex as a delegating parent needs --provider (and --model): its private folder has none of your ChatGPT login")
            home = parent_home(mode)
            files[str(home / "instructions.md")] = prompts.DELEGATING
            files[str(home / "rules" / "default.rules")] = RULES
            argv += ["--ephemeral", "-s", "read-only"]
            for f in FEATURES_OFF:
                argv += ["--disable", f]
            for c in (*LEAN_CONFIG, "model_instructions_file=" + json.dumps(str(home / "instructions.md"))):
                argv += ["-c", c]
            env["CODEX_HOME"] = str(home)
            notes = [*notes, *NOTES]
        else:
            argv += ["-s", "workspace-write", "-c", 'approval_policy="never"']
            if provider:
                argv += ["--ephemeral"]
        argv.append("-")                                                # the task on stdin
        if bridge:                                                      # the wrapper starts the bridge, fills in its address, runs Codex and stops the bridge
            argv = [sys.executable, "-m", "gruntly.responsesbridge", "--upstream", bridge[0], "--key-env", bridge[1], "--", *argv]
        return ParentCommand(argv=argv, env=env, stdin=task, files=files, notes=notes)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParentOutcome:
        text, session, tot, failure, turns = parse_events(stdout)
        if not text and not failure and not tot:
            return ParentOutcome(final_message=((stderr or stdout or "").strip()[-600:] or "no output"), is_error=True)
        usage = Usage(prompt=tot["input_tokens"], completion=tot["output_tokens"], cached=tot["cached_input_tokens"], requests=turns) if tot else None
        return ParentOutcome(final_message=text or failure, is_error=bool(failure) or exit_code != 0, session_id=session, usage=usage, turns=turns or None)

    def capabilities(self) -> ParentCaps:
        return ParentCaps(replace_system_prompt=True, restrict_tools=False, restrict_shell=True, disable_extensions=True, reports_usage=True,
                          reports_cost=False, notes=NOTES + ("works with any chat provider through gruntly's Responses-to-chat bridge, or directly with one that serves the Responses API",))

    def cancel(self, proc) -> None:
        kill_tree(proc)
