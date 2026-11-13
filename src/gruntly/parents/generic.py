"""A parent for any command-line harness gruntly has no adapter for, described in your settings: `[parent.generic]` in `~/.config/gruntly/config.toml`
or the project's `.gruntly.toml` (the project wins).

    [parent.generic]
    command = ["myagent", "--system-file", "{system_file}", "--model", "{model}", "--print"]    # argv template, or one string
    working_command = ["myagent", "--yolo", "--print"]       # optional: for --mode working (default: `command`)
    task = "stdin"                                           # "stdin" (default) or "arg" (the task fills {task})
    system = "file"                                          # how the delegating prompt is delivered: "file" ({system_file}), "arg" ({system}), "none"
    output = "text"                                          # "text": stdout is the answer; "json:KEY": a key of the JSON object on stdout (dots descend)
    [parent.generic.caps]                                    # what the tool really does of the lean setup: you declare it, nothing is assumed
    replace_system_prompt = true
    restrict_tools = true
    restrict_shell = false

Placeholders: {task} {system} {system_file} {model} {provider} {base_url}. A named catalog provider also passes its key in the environment (under
its own variable name, and as OPENAI_API_KEY with OPENAI_BASE_URL / OPENAI_API_BASE for OpenAI-compatible tools), never on the command line. What
you do not declare in `caps` is reported as not done, so a generic parent is never claimed to be lean when nobody checked. No tokens or dollars
come back from it. To check what a harness really sends before you declare anything, point it at the stub server in `gruntly/probe.py`, as the
tests for the other parents do.
"""
from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

from .. import providers
from ..store import state_dir
from . import prompts
from .base import Detection, ParentCaps, ParentCommand, ParentOutcome, check_mode, kill_tree, which

CAPS = ("replace_system_prompt", "restrict_tools", "restrict_shell", "disable_extensions")


def load(root=None) -> dict:
    """The `[parent.generic]` table: global settings first, then the project's `.gruntly.toml` over it, field by field."""
    from ..spec import _toml, global_config_path
    out: dict = {}
    for p in (global_config_path(), (Path(root) if root else Path.cwd()) / ".gruntly.toml"):
        if p.is_file():
            t = (_toml(p).get("parent") or {}).get("generic")
            if isinstance(t, dict):
                out.update({k: (({**out.get(k, {}), **v}) if k == "caps" and isinstance(v, dict) else v) for k, v in t.items()})
    return out


def _argv(tpl) -> list[str]:
    if isinstance(tpl, (list, tuple)):
        return [str(x) for x in tpl]
    return shlex.split(str(tpl), posix=(os.name != "nt"))


class GenericParent:
    name = "generic"

    def detect(self) -> Detection:
        cfg = load()
        if not cfg.get("command"):
            return Detection(False, None, "no [parent.generic] command in your settings (see `gruntly/parents/generic.py` for the table)")
        exe = _argv(cfg["command"])[0]
        return Detection(bool(which(exe) or Path(exe).is_file()), None, "" if (which(exe) or Path(exe).is_file()) else f"{exe} not found")

    def command(self, task: str, mode: str, model: str | None = None, provider: str | None = None, structured: bool = False) -> ParentCommand:
        check_mode(mode)
        cfg = load()
        tpl = (cfg.get("working_command") if mode == "working" else None) or cfg.get("command")
        if not tpl:
            raise ValueError("the generic parent needs a command: add [parent.generic] command = [...] to your settings (see `gruntly/parents/generic.py`)")
        base_url, env = "", {}
        if provider:
            p = providers.ALL.get(provider)
            if p is None:
                raise ValueError(f"unknown provider {provider!r}; known: {', '.join(providers.ALL)}")
            base_url = p.base_url
            key = "local"
            if p.kind != "local":
                key = providers.api_key(p)
                if not key:
                    raise ValueError(f"no API key for {p.name}: run `gruntly auth set {p.name}` (or set {p.key_env})")
                env[p.key_env] = key
            env.update({"OPENAI_API_KEY": key, "OPENAI_BASE_URL": base_url, "OPENAI_API_BASE": base_url})
            model = model or p.default_model
        delegating = mode == "delegating"
        how = str(cfg.get("system", "file")) if delegating else "none"
        files: dict[str, str] = {}
        system_file = ""
        if how == "file":
            system_file = str(state_dir() / "generic-parent" / "system.md")
            files[system_file] = prompts.DELEGATING
        subs = {"task": task if cfg.get("task") == "arg" else "", "system": prompts.DELEGATING if how == "arg" else "", "system_file": system_file,
                "model": model or "", "provider": provider or "", "base_url": base_url}
        argv = []
        for part in _argv(tpl):
            for k, v in subs.items():
                part = part.replace("{" + k + "}", v)
            argv.append(part)
        notes = [] if not delegating else [f"{k} is not declared for this parent, so it is treated as not done" for k in CAPS if not (cfg.get("caps") or {}).get(k)]
        return ParentCommand(argv=argv, env=env, stdin=None if cfg.get("task") == "arg" else task, files=files, notes=notes)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParentOutcome:
        spec = str(load().get("output", "text"))
        text = (stdout or "").strip()
        if spec.startswith("json:"):
            try:
                node = json.loads(text[text.find("{"):] if "{" in text else text)
                for k in spec[5:].split("."):
                    node = node[k]
                text = str(node).strip()
            except (ValueError, KeyError, TypeError):
                return ParentOutcome(final_message=(stderr or stdout or "").strip()[-600:] or f"no `{spec[5:]}` in the output", is_error=True)
        if exit_code != 0:
            return ParentOutcome(final_message=(text or stderr or "").strip()[-600:] or f"exit code {exit_code}", is_error=True)
        return ParentOutcome(final_message=text[-2000:], is_error=not text)

    def capabilities(self) -> ParentCaps:
        c = load().get("caps") or {}
        return ParentCaps(**{k: bool(c.get(k)) for k in CAPS}, reports_usage=False, reports_cost=False, experimental=True,
                          notes=("described in your settings: the lean setup is only as real as what you declare and checked",))

    def cancel(self, proc) -> None:
        kill_tree(proc)
