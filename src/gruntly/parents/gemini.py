"""Gemini CLI as a parent (checked against 0.68.0, the real binary talking to a stub that speaks the Gemini API, see
gruntly/probe.py: no key, no cost).

**Delegating** runs from a private `GEMINI_CLI_HOME` (gruntly's state folder) that holds two files gruntly writes before launch:
`system.md`, our prompt, named by `GEMINI_SYSTEM_MD` (the model received exactly it, 1,548 characters, in place of about 30,400), and
`.gemini/settings.json`, which selects the API-key login and sets `tools.core` to `["run_shell_command(gruntly)"]`. Measured: the tools offered
went from eight to one (`run_shell_command`), and with `--approval-mode yolo` a command is run only if it starts with `gruntly`: a write, a read
and a chained command all came back "Tool execution denied by policy". **Working** is Gemini CLI as shipped with `--approval-mode yolo`.

Gemini CLI speaks the Gemini API only (`GOOGLE_GEMINI_BASE_URL` can point it at another server of that API), so the only catalog provider is
`gemini`, and delegating needs it: the private folder holds none of your own login. A `GEMINI.md` in the project may still be read (not checked).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .. import providers
from ..store import state_dir
from ..usage import Usage
from . import prompts
from .base import Detection, ParentCaps, ParentCommand, ParentOutcome, check_mode, kill_tree, which

NOTES = ("Gemini CLI speaks only the Gemini API: the provider is gemini", "a GEMINI.md in the project may still be read (not checked)",
         "tools.core leaves only the shell tool; MCP servers in a project's settings were not tried")
SETTINGS = {"security": {"auth": {"selectedType": "gemini-api-key"}}, "tools": {"core": ["run_shell_command(gruntly)"]}}


def parent_home(mode: str = "delegating") -> Path:
    shared = os.environ.get("GRUNTLY_GEMINI_PARENT_HOME")
    return (Path(shared) if shared else state_dir() / "gemini-parent") / mode


def provider_setup(provider: str | None) -> dict[str, str]:
    """Environment for the Gemini API login. Only the catalog's `gemini` provider (or none, for your own login in working mode) fits."""
    if not provider:
        return {}
    p = providers.ALL.get(provider)
    if p is None:
        raise ValueError(f"unknown provider {provider!r}; known: {', '.join(providers.ALL)}")
    if p.name != "gemini":
        raise ValueError(f"Gemini CLI speaks only the Gemini API, so the provider can only be gemini, not {p.name}")
    key = providers.api_key(p)
    if not key:
        raise ValueError(f"no API key for gemini: run `gruntly auth set gemini` (or set {p.key_env})")
    return {"GEMINI_API_KEY": key}                           # in the environment, never on the command line


class GeminiParent:
    name = "gemini"

    def detect(self) -> Detection:
        exe = which("gemini")
        if not exe:
            return Detection(False, None, "gemini not on PATH (npm i -g @google/gemini-cli)")
        try:
            out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
        except Exception as e:  # noqa: BLE001
            return Detection(True, None, f"version check failed: {e}")
        return Detection(True, out.splitlines()[-1].strip() if out else None)

    def command(self, task: str, mode: str, model: str | None = None, provider: str | None = None, structured: bool = False) -> ParentCommand:
        check_mode(mode)
        env = provider_setup(provider)
        argv = [which("gemini") or "gemini", "--skip-trust", "--approval-mode", "yolo", "-o", "json", "-p", " "]      # the task on stdin, `-p` is appended to it
        if model:
            argv += ["-m", model]
        files: dict[str, str] = {}
        notes: list[str] = []
        if mode == "delegating":
            if not provider:
                raise ValueError("Gemini CLI as a delegating parent needs --provider gemini (and a Gemini API key): its private folder has none of your own login")
            home = parent_home(mode)
            files[str(home / "system.md")] = prompts.DELEGATING
            files[str(home / ".gemini" / "settings.json")] = json.dumps(SETTINGS, indent=2)
            env["GEMINI_CLI_HOME"] = str(home)
            env["GEMINI_SYSTEM_MD"] = str(home / "system.md")
            notes += list(NOTES)
        return ParentCommand(argv=argv, env=env, stdin=task, files=files, notes=notes)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParentOutcome:
        s = (stdout or "").strip()
        data = None
        for cand in (s, s[s.find("{"):] if "{" in s else ""):
            try:
                data = json.loads(cand)
                break
            except ValueError:
                continue
        if not isinstance(data, dict):
            return ParentOutcome(final_message=((stderr or stdout or "").strip()[-600:] or "no output"), is_error=True)
        err = data.get("error")
        if err:
            return ParentOutcome(final_message=str(err.get("message") if isinstance(err, dict) else err), is_error=True, session_id=data.get("session_id"))
        usage = Usage()
        models = (data.get("stats") or {}).get("models") or {}
        for m in models.values():
            t, a = m.get("tokens") or {}, m.get("api") or {}
            usage.add(Usage(prompt=int(t.get("prompt") or t.get("input") or 0), completion=int(t.get("candidates") or 0), cached=int(t.get("cached") or 0),
                            reasoning=int(t.get("thoughts") or 0), requests=int(a.get("totalRequests") or 0)))
        return ParentOutcome(final_message=str(data.get("response") or "").strip(), is_error=exit_code != 0, session_id=data.get("session_id"),
                             usage=usage if usage.requests else None, turns=usage.requests or None)

    def capabilities(self) -> ParentCaps:
        return ParentCaps(replace_system_prompt=True, restrict_tools=True, restrict_shell=True, disable_extensions=False, reports_usage=True,
                          reports_cost=False, notes=NOTES)

    def cancel(self, proc) -> None:
        kill_tree(proc)
