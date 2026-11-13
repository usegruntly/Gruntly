"""Qwen Code as a parent (checked against 0.26.9, the real binary talking to a stub model server, see gruntly/probe.py: no key, no cost).

**Delegating**: `--bare` (no implicit auto-discovery of context files, extensions, MCP servers, hooks), `--system-prompt` with the delegating
prompt (the model received exactly it, 1,548 characters), `--exclude-tools` for every tool but the shell (the tools offered went from six to
`run_shell_command`), and `--approval-mode default --allowed-tools run_shell_command(gruntly)`. Qwen has no allow-list for commands, so the
restriction is what its permission rules do with the tools that were excluded: a shell command that would write a file (`touch`, a
redirect), read one (`cat`) or chain a second command after gruntly is refused ("denied by permission rules"), an interpreter
(`python -c ...`) is declined because headless mode cannot ask, and `gruntly ...` runs. A command that touches no file (`echo`) still runs.
**Working** is Qwen as shipped with every tool approved.

`--bare` is documented to leave extensions and MCP out; only the tool list was checked here. Your own login and default model are used
unless a provider is named; a catalog provider is passed as an OpenAI-compatible endpoint, its key in the environment.
"""
from __future__ import annotations

from .. import providers
from ..adapters.qwen import QwenAdapter
from ..usage import Usage
from . import prompts
from .base import Detection, ParentCaps, ParentCommand, ParentOutcome, check_mode, kill_tree, which

EXCLUDED = ("edit", "read_file", "notebook_edit", "get_goal", "update_goal")     # every tool `--bare` offers except run_shell_command
TURNS = 16                                                                       # a delegating parent needs a handful
WALL_S = 900
NOTES = ("a command that touches no file (echo) still runs; writes, reads, interpreters and chained commands are refused",
         "--bare is documented to leave extensions and MCP out; only the tool list was checked")


def provider_setup(provider: str | None, model: str | None) -> tuple[list[str], dict[str, str]]:
    """(flags, environment) that point Qwen at a catalog provider as an OpenAI-compatible endpoint. No provider: its own login and
    default, and `model` is passed as given."""
    if not provider:
        return (["-m", model] if model else []), {}
    p = providers.ALL.get(provider)
    if p is None:
        raise ValueError(f"unknown provider {provider!r}; known: {', '.join(providers.ALL)}")
    key = "local"
    if p.kind != "local":
        key = providers.api_key(p)
        if not key:
            raise ValueError(f"no API key for {p.name}: run `gruntly auth set {p.name}` (or set {p.key_env})")
    use = model or p.default_model
    if not use:
        raise ValueError(f"provider {p.name} has no default model: pass --model ID (see `gruntly models {p.name}`)")
    return ["--auth-type", "openai", "-m", use], {"OPENAI_BASE_URL": p.base_url, "OPENAI_API_KEY": key}      # the key in the environment, never on the command line


class QwenParent:
    name = "qwen"

    def detect(self) -> Detection:
        return QwenAdapter().detect()

    def command(self, task: str, mode: str, model: str | None = None, provider: str | None = None, structured: bool = False) -> ParentCommand:
        check_mode(mode)
        flags, env = provider_setup(provider, model)
        env["QWEN_CODE_SUPPRESS_YOLO_WARNING"] = "1"
        argv = [which("qwen") or "qwen", *flags, "-o", "json", "--max-wall-time", str(WALL_S)]
        notes: list[str] = []
        if mode == "delegating":
            argv += ["--bare", "--system-prompt", prompts.DELEGATING, "--approval-mode", "default", "--allowed-tools", "run_shell_command(gruntly)",
                     "--exclude-tools", *EXCLUDED, "--max-session-turns", str(TURNS)]
            notes += list(NOTES)
        else:
            argv += ["--approval-mode", "yolo"]
        return ParentCommand(argv=argv, env=env, stdin=task, notes=notes)             # the task on stdin: the npm .cmd shim mangles multi-line arguments

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParentOutcome:
        c = QwenAdapter().parse(stdout, stderr, exit_code)
        u = c.usage if c.usage.get("available") else None
        usage = Usage(prompt=u.get("input_tokens") or 0, completion=u.get("output_tokens") or 0, requests=u.get("requests") or 0) if u else None
        return ParentOutcome(final_message=c.final_message, is_error=c.is_error, session_id=c.session_id, usage=usage, turns=(u or {}).get("requests"))

    def capabilities(self) -> ParentCaps:
        return ParentCaps(replace_system_prompt=True, restrict_tools=True, restrict_shell=True, disable_extensions=True, reports_usage=True,
                          reports_cost=False, notes=NOTES)

    def cancel(self, proc) -> None:
        kill_tree(proc)
