"""Hermes Agent as a parent (checked against 0.23.0, the real binary talking to a stub model server, see gruntly/probe.py: no key, no cost).

**Delegating**: Hermes reads its identity from `SOUL.md` in its data folder, so gruntly keeps a private folder for the parent and puts the
delegating prompt there; `-t terminal` leaves the shell toolset (Hermes adds three small tool-lookup tools beside it, four tools instead of
twenty). Measured: the system prompt went from about 9,900 characters to about 6,250, of which about 950 are ours at the head; the other
5,300 are Hermes's own guidance and environment notes, which no flag removes. (`--ignore-rules` would skip SOUL.md too, so it is not used.)
**Working** is Hermes as shipped with `--yolo`.

What Hermes cannot do, said in the capability record and `ParentCommand.notes`: replace its whole system prompt, and allow only `gruntly`
commands (its terminal tool ran `touch` and `cat` in the check). The delegating prompt tells it not to; nothing enforces it.

The private folder needs Hermes's dependency environment once: `HERMES_HOME=<folder> hermes pm repair` (the error says so). It holds the
provider config (a `key_env` reference, never the key) and `SOUL.md`. Hermes sends the placeholder `no-key-required` to every local
endpoint, so a stub on localhost cannot show that `key_env` delivers a key to a hosted provider: that part stays experimental until a live
check with a real key. With no provider named, delegating needs a config already in the
folder (your own login copied there); working mode uses your own Hermes as it is.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .. import providers
from ..adapters.hermes import ANSI, UTF8, HermesAdapter, find_hermes
from ..store import state_dir
from ..usage import Usage
from . import prompts
from .base import Detection, ParentCaps, ParentCommand, ParentOutcome, check_mode, kill_tree

PROVIDER = "gruntly"
TURNS = 16
NOTES = ("Hermes keeps about 5,300 characters of its own guidance after ours", "the shell is not restricted to gruntly commands: the prompt asks, nothing enforces it",
         "the private data folder needs `hermes pm repair` once",
         "a hosted provider's key is passed through `key_env` as Hermes documents it; not checked, because Hermes sends `no-key-required` to any local endpoint")


def parent_home(mode: str = "delegating") -> Path:
    """The private Hermes data folder for the parent (`GRUNTLY_HERMES_PARENT_HOME` names one; otherwise under gruntly's state folder).
    A separate folder per mode, so the working one never carries the delegating `SOUL.md`."""
    shared = os.environ.get("GRUNTLY_HERMES_PARENT_HOME")
    base = Path(shared) if shared else state_dir() / "hermes-parent"
    return base / mode


def config_text(base_url: str, model: str, key_env: str | None) -> str:
    """Hermes's config for one OpenAI-compatible endpoint. The key is named by environment variable (`key_env`), never written. JSON strings
    are valid YAML scalars, so values need no quoting rules."""
    key = f"    key_env: {json.dumps(key_env)}\n" if key_env else '    api_key: "local"\n'
    return ("custom_providers:\n" f"  - name: {PROVIDER}\n" f"    base_url: {json.dumps(base_url)}\n" + key + f"    model: {json.dumps(model)}\n"
            "model:\n" f"  provider: custom:{PROVIDER}\n" f"  default: {json.dumps(model)}\n")


def provider_setup(provider: str | None, model: str | None) -> tuple[str | None, str | None, dict[str, str]]:
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
    return config_text(p.base_url, use, key_env), use, env


class HermesParent:
    name = "hermes"

    def detect(self) -> Detection:
        return HermesAdapter().detect()

    def command(self, task: str, mode: str, model: str | None = None, provider: str | None = None, structured: bool = False) -> ParentCommand:
        check_mode(mode)
        cfg, use, env = provider_setup(provider, model)
        argv = [find_hermes() or "hermes", "chat", "-Q", "--query-file", "-", "--format", "stream-json"]
        files: dict[str, str] = {}
        notes: list[str] = []
        env = {**env, **UTF8}
        home = parent_home(mode)
        if mode == "delegating":
            if cfg is None and not (home / "config.yaml").is_file():
                raise ValueError(f"Hermes as a delegating parent needs --provider (and --model): its private folder {home} has no login of its own")
            argv += ["-t", "terminal", "--max-turns", str(TURNS)]
            files[str(home / "SOUL.md")] = prompts.DELEGATING
            notes += list(NOTES)
        else:
            argv += ["--yolo"]
        if cfg is not None:
            files[str(home / "config.yaml")] = cfg
            argv += ["--provider", f"custom:{PROVIDER}", "-m", use]
        elif use:
            argv += ["-m", use]
        if cfg is not None or mode == "delegating":
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
                text = "Hermes's data folder has no dependency environment: run `hermes pm repair` with HERMES_HOME set to it (see docs/parents.md)"
            return ParentOutcome(final_message=text[-600:], is_error=True)
        m = re.search(r"session_id:\s*(\S+)", err)
        t = res.get("tokens") if isinstance(res.get("tokens"), dict) else {}
        usage = Usage(prompt=int(t.get("input") or 0), completion=int(t.get("output") or 0)) if t else None
        return ParentOutcome(final_message=str(res.get("text") or "").strip(), is_error=bool(res.get("exit_code")) or exit_code != 0,
                             session_id=res.get("session_id") or (m.group(1) if m else None), usage=usage)

    def capabilities(self) -> ParentCaps:
        return ParentCaps(replace_system_prompt=False, restrict_tools=True, restrict_shell=False, disable_extensions=False, reports_usage=True,
                          reports_cost=False, experimental=True, notes=NOTES)      # experimental: key delivery to a hosted provider is not checked live

    def cancel(self, proc) -> None:
        kill_tree(proc)
