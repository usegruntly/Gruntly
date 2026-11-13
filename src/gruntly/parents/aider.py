"""Aider as a parent (checked against 0.86.2, the real binary talking to a stub model server, see gruntly/probe.py: no key, no cost).

**Working only.** Aider is not a tool-calling agent: it sends the model a prompt of its own per edit format, applies the edits the model
writes, and can run a shell command only when the model suggests one in a fenced block (and then only with `--yes-always`, any command).
It has no setting that replaces that prompt and none that limits which commands run, so it cannot be the lean delegating parent, which is
a model that is shown one tool and one rule. `--mode delegating` says so and stops; use Aider as a child (`harness = "aider"`) or as the
parent in `--mode working`.

Working runs `aider --message-file` with `--yes-always`, no auto-commits (the diff stays in your tree for you to look at), and none of the
things that talk to anyone but the model (update check, analytics) or wait for a person (fancy input, pretty output). A catalog provider is
an OpenAI-compatible endpoint (`openai/<model>` with `OPENAI_API_BASE` and `OPENAI_API_KEY` in the environment); with none, your own Aider
configuration and keys are used.
"""
from __future__ import annotations

import subprocess

from .. import nobrowser, providers
from ..adapters.aider import parse_output
from ..store import state_dir
from ..usage import Usage
from .base import Detection, ParentCaps, ParentCommand, ParentOutcome, check_mode, kill_tree, which

WORKING_NOTES = ("Aider writes its history files (.aider*) into the project and may add them to .gitignore, as it does when you run it by hand",)
NOTES = ("Aider has no tool loop, no prompt override and no command limit, so it cannot be a delegating parent",)


def provider_setup(provider: str | None, model: str | None) -> tuple[list[str], dict[str, str]]:
    """(the `--model` flags, environment) for a catalog provider as an OpenAI-compatible endpoint. No provider: Aider's own configuration."""
    if not provider:
        return (["--model", model] if model else []), {}
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
    return ["--model", f"openai/{use}"], {"OPENAI_API_BASE": p.base_url, "OPENAI_API_KEY": key}          # the key in the environment only


class AiderParent:
    name = "aider"

    def detect(self) -> Detection:
        exe = which("aider")
        if not exe:
            return Detection(False, None, "aider not on PATH (python -m pip install aider-chat)")
        try:
            out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
        except Exception as e:  # noqa: BLE001
            return Detection(True, None, f"version check failed: {e}")
        return Detection(True, out.split()[-1] if out else None)

    def command(self, task: str, mode: str, model: str | None = None, provider: str | None = None, structured: bool = False) -> ParentCommand:
        check_mode(mode)
        if mode == "delegating":
            raise ValueError("Aider cannot be a delegating parent: it has no tool loop, no way to replace its prompt and no limit on the commands it may run. "
                             "Use `--mode working`, or use Aider as the child (harness = \"aider\")")
        flags, env = provider_setup(provider, model)
        msg = state_dir() / "aider-parent" / "message.txt"
        argv = [which("aider") or "aider", *flags, "--message-file", str(msg), "--yes-always", "--no-auto-commits", "--no-check-update", "--no-analytics",
                "--no-show-model-warnings", "--no-pretty", "--no-stream", "--no-fancy-input", "--no-detect-urls", "--no-restore-chat-history"]
        env = {**env, "PYTHONIOENCODING": "utf-8", "AIDER_ANALYTICS": "false", **nobrowser.env()}     # --yes-always also opens every "Open URL?" offer: see gruntly/nobrowser.py
        return ParentCommand(argv=argv, env=env, stdin=None, files={str(msg): task}, notes=list(WORKING_NOTES))

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParentOutcome:
        text, sent, recv, n = parse_output(stdout)
        usage = Usage(prompt=sent, completion=recv, requests=n) if n else None
        if exit_code != 0 or not text:
            return ParentOutcome(final_message=(text or (stderr or "").strip())[-600:] or "no output", is_error=True, usage=usage)
        return ParentOutcome(final_message=text[-2000:], is_error=False, usage=usage, turns=n or None)

    def capabilities(self) -> ParentCaps:
        return ParentCaps(replace_system_prompt=False, restrict_tools=False, restrict_shell=False, disable_extensions=False, reports_usage=True,
                          reports_cost=False, modes=("working",), notes=NOTES)

    def cancel(self, proc) -> None:
        kill_tree(proc)
