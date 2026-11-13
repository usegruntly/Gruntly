"""Hermes Agent as a parent (checked against 0.23.0, the real binary talking to a stub model server, see gruntly/probe.py: no key, no cost, and live on free tiers).

**Delegating** gives Hermes no shell at all. Its only tools are gruntly's own, through gruntly's MCP server (`gruntly mcp`: `gruntly_delegate` and `gruntly_manage`),
so "only gruntly commands" holds by construction, not because a prompt asks: there is no `terminal`, `read_file` or `patch` tool to misuse (an earlier version
gave it the terminal toolset, and the shell ran `touch` and `cat`). gruntly keeps a private data folder for the parent and writes its config there:
  * `mcp_servers.gruntly` with `env.GRUNTLY_MCP_REQUIRE_REPO: 1`, `tools.include` the two tools and `prompts` / `resources` off (Hermes still adds four inert helper tools, `get_prompt`,
    `list_prompts`, `list_resources` and `read_resource`, none of which touches files or runs commands), run with `-t mcp-gruntly`;
  * `gateway.unmanaged_idle_exit_seconds: 2`: Hermes runs the agent inside a background gateway process and resolves `key_env` from THAT process's environment; the
    gateway one chat starts is shared by the next chats in the same folder for 10 minutes, so a later run with another provider or key would reach it without its key
    (seen live: a stub test's gateway answered the next real run with a 401). A gateway that exits two seconds after its last client gives every run its own;
  * `tools.tool_search.enabled: "off"`, so the two tools are offered directly instead of behind three lookup tools;
  * the optional prompt sections off (tool-use and execution guidance, task completion and parallel-call text, the toolchain probe, bot mode, the coding brief,
    memory and the user profile, the platform hint), and our prompt, the tool-calling variant `DELEGATING_TOOL`, as `SOUL.md`, Hermes's identity file.
Hermes hosts MCP servers in a background gateway that outlives the chat and is shared by later chats in the same folder, so nothing per-run can travel in the server's
environment (a `${workspaceFolder}` there was resolved once, for the first chat, and the server then worked in the wrong folder). Instead the prompt names the repository
(written fresh at each launch) and the server, told to require it, refuses a call that does not pass `repo`. Measured: 20 tools and about 9,900 characters of system prompt by default; 6 tools and about 4,800 here, of which about 1,600 are ours at the head. What remains is
Hermes's own help pointer and runtime-environment notes, which no setting removes (`--ignore-rules` would skip `SOUL.md` too, so it is not used).
**Working** is Hermes as shipped with `--yolo`, your own login and home.

The private folder needs Hermes's dependency environment once (`gruntly parent prepare hermes`, which runs `hermes pm repair` with `HERMES_HOME` set to it; the
error says so). Its config names the provider's key by environment variable (`key_env`), never the key. Hermes sends the placeholder `no-key-required` to every
local endpoint, so a stub on localhost cannot show a key arriving; the live checks with NVIDIA's and Gemini's free keys do. Delegating needs `--provider`: the folder holds none of
your own logins.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .. import providers
from ..adapters.hermes import ANSI, UTF8, HermesAdapter, find_hermes
from ..store import state_dir
from ..usage import Usage
from . import prompts
from .base import Detection, ParentCaps, ParentCommand, ParentOutcome, check_mode, kill_tree

PROVIDER = "gruntly"
TURNS = 16
TOOLSET = "mcp-gruntly"                         # Hermes names the runtime toolset of an MCP server mcp-<server>
GRUNTLY_TOOLS = ("gruntly_delegate", "gruntly_manage")
# {gruntly_cwd} is filled in with the folder the parent is launched in when the file is written (parents.base.run); forward slashes need no escaping in a tool call.
REPO_SENTENCE = " The repository to work in is {gruntly_cwd}: pass it as the repo argument of every gruntly_delegate and gruntly_manage call."
NOTES = ("its only tools are gruntly's two MCP tools plus four inert MCP helper tools Hermes adds (list and read prompts and resources); there is no shell",
         "Hermes keeps about 3,200 characters of its own help pointer and environment notes after ours",
         "the private data folder needs `hermes pm repair` once: `gruntly parent prepare hermes`")

# The optional prompt sections and extras switched off for the lean parent (each is a documented key of config.yaml).
LEAN_YAML = """gateway:
  unmanaged_idle_exit_seconds: 2
tools:
  tool_search:
    enabled: "off"
agent:
  tool_use_enforcement: false
  execution_guidance: false
  task_completion_guidance: false
  parallel_tool_call_guidance: false
  environment_probe: false
  bot_mode_protocol: false
  coding_context: "off"
memory:
  memory_enabled: false
  user_profile_enabled: false
platform_hints:
  cli:
    replace: ""
"""


def parent_home(mode: str = "delegating") -> Path:
    """The private Hermes data folder for the parent (`GRUNTLY_HERMES_PARENT_HOME` names one). A separate folder per mode, so the working one never carries the delegating
    `SOUL.md`. On Windows the default is SHORT (`~/.ghp/d`): Hermes builds an environment inside the folder whose paths nest about 200 characters deep and Windows stops at
    260, so gruntly's usual state folder was too long (`hermes pm repair` failed there with WinError 3; a 23-character folder worked)."""
    shared = os.environ.get("GRUNTLY_HERMES_PARENT_HOME")
    if shared:
        return Path(shared) / mode
    if os.name == "nt":
        return Path.home() / ".ghp" / mode[0]
    return state_dir() / "hermes-parent" / mode


def mcp_yaml() -> str:
    """The `mcp_servers` entry that runs gruntly's own MCP server with this Python (JSON strings are valid YAML scalars)."""
    return ("mcp_servers:\n  gruntly:\n    command: " + json.dumps(sys.executable) + "\n    args: [\"-m\", \"gruntly\", \"mcp\"]\n"
            "    env:\n      GRUNTLY_MCP_REQUIRE_REPO: \"1\"\n"                          # the server outlives the project (see the module docstring): it never guesses the repository
            "    tools:\n      include: " + json.dumps(list(GRUNTLY_TOOLS)) + "\n      prompts: false\n      resources: false\n")


def config_text(base_url: str, model: str, key_env: str | None, delegating: bool = False) -> str:
    """Hermes's config for one OpenAI-compatible endpoint. The key is named by environment variable (`key_env`), never written. With `delegating`
    the lean parts are added: gruntly's MCP server as the only tools, tool search off, the optional prompt sections off."""
    key = f"    key_env: {json.dumps(key_env)}\n" if key_env else '    api_key: "local"\n'
    text = ("custom_providers:\n" f"  - name: {PROVIDER}\n" f"    base_url: {json.dumps(base_url)}\n" + key + f"    model: {json.dumps(model)}\n"
            "model:\n" f"  provider: custom:{PROVIDER}\n" f"  default: {json.dumps(model)}\n")
    return text + (mcp_yaml() + LEAN_YAML if delegating else "")


def provider_setup(provider: str | None, model: str | None, delegating: bool = False) -> tuple[str | None, str | None, dict[str, str]]:
    """(the config text, the model, environment to add) for a catalog provider; (None, model, {}) without one."""
    if not provider:
        return None, model, {}
    p = providers.ALL.get(provider)
    if p is None:
        raise ValueError(f"unknown provider {provider!r}; known: {', '.join(providers.ALL)}")
    env: dict[str, str] = {}
    key_env = None
    if p.kind != "local":
        key = providers.api_key(p)
        if not key:
            raise ValueError(f"no API key for {p.name}: run `gruntly auth set {p.name}` (or set {p.key_env})")
        env[p.key_env] = key
        key_env = p.key_env
    use = model or p.default_model
    if not use:
        raise ValueError(f"provider {p.name} has no default model: pass --model ID (see `gruntly models {p.name}`)")
    return config_text(p.base_url, use, key_env, delegating), use, env


def prepare(mode: str = "delegating", timeout_s: int = 900) -> tuple[bool, str]:
    """Give the private data folder Hermes's dependency environment (`hermes pm repair` with HERMES_HOME set to it): needed once per folder, takes a minute or two
    and downloads Python packages. Returns (ok, the tail of its output)."""
    exe = find_hermes()
    if not exe:
        return False, "hermes is not installed: " + HermesAdapter().detect().detail
    home = parent_home(mode)
    home.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run([exe, "pm", "repair"], capture_output=True, text=True, encoding="utf8", errors="replace", timeout=timeout_s,
                           env={**os.environ, "HERMES_HOME": str(home), **UTF8})
    except subprocess.TimeoutExpired:
        return False, f"hermes pm repair did not finish in {timeout_s} s"
    out = ANSI.sub("", (p.stdout or "") + (p.stderr or "")).strip()
    if p.returncode != 0 and "WinError 3" in out:
        return False, (f"Windows stopped at its 260-character path limit inside {home}: Hermes's environment nests too deeply for that folder. Pick a shorter one "
                       "(set GRUNTLY_HERMES_PARENT_HOME, for example to C:\\gh) and run this again, or turn on Windows long paths.")
    return p.returncode == 0, "\n".join(out.splitlines()[-6:])


class HermesParent:
    name = "hermes"

    def detect(self) -> Detection:
        return HermesAdapter().detect()

    def command(self, task: str, mode: str, model: str | None = None, provider: str | None = None, structured: bool = False) -> ParentCommand:
        check_mode(mode)
        delegating = mode == "delegating"
        if delegating and not provider:
            raise ValueError("Hermes as a delegating parent needs --provider (and --model): its private folder has none of your own logins")
        cfg, use, env = provider_setup(provider, model, delegating)
        argv = [find_hermes() or "hermes", "chat", "-Q", "--query-file", "-", "--format", "stream-json"]
        files: dict[str, str] = {}
        notes: list[str] = []
        env = {**env, **UTF8}
        home = parent_home(mode)
        if delegating:
            argv += ["-t", TOOLSET, "--max-turns", str(TURNS)]
            files[str(home / "SOUL.md")] = prompts.DELEGATING_TOOL + REPO_SENTENCE
            notes += list(NOTES)
        else:
            argv += ["--yolo"]
        if cfg is not None:
            files[str(home / "config.yaml")] = cfg
            argv += ["--provider", f"custom:{PROVIDER}", "-m", use]
        elif use:
            argv += ["-m", use]
        if cfg is not None:
            env["HERMES_HOME"] = str(home)
        return ParentCommand(argv=argv, env=env, stdin=task, files=files, notes=notes)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParentOutcome:
        out, err = ANSI.sub("", stdout or ""), ANSI.sub("", stderr or "")
        events = []
        for line in out.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        res = next((e for e in reversed(events) if isinstance(e, dict) and e.get("type") == "result"), None)
        if res is None:
            text = (err or out).strip()
            if "hermes pm repair" in text:
                text = "Hermes's data folder has no dependency environment: run `gruntly parent prepare hermes` (it runs `hermes pm repair` for the folder)"
            return ParentOutcome(final_message=text[-600:], is_error=True)
        m = re.search(r"session_id:\s*(\S+)", err)
        t = res.get("tokens") if isinstance(res.get("tokens"), dict) else {}
        usage = Usage(prompt=int(t.get("input") or 0), completion=int(t.get("output") or 0), cached=int(t.get("cache_read") or 0),
                      cache_write=int(t.get("cache_write") or 0)) if t else None
        return ParentOutcome(final_message=str(res.get("text") or "").strip(), is_error=bool(res.get("exit_code")) or exit_code != 0,
                             session_id=res.get("session_id") or (m.group(1) if m else None), usage=usage)

    def capabilities(self) -> ParentCaps:
        return ParentCaps(replace_system_prompt=False, restrict_tools=True, restrict_shell=True, disable_extensions=True, reports_usage=True,
                          reports_cost=False, notes=NOTES)      # live: a real model on NVIDIA's free tier delegated a fix through the MCP tools

    def cancel(self, proc) -> None:
        kill_tree(proc)
