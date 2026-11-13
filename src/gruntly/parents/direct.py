"""The direct parent: no harness, a short loop of gruntly's own (`gruntly/direct.py`) that calls an OpenAI-compatible chat API with the
delegating prompt and one tool that runs `gruntly` commands and nothing else (no shell: nothing can be chained, piped or redirected). Any catalog
provider or local server works, as long as the model supports tool calls. Delegating only: it has no tools with which to do the job itself.

It is the one parent whose cost gruntly can work out itself: it sees every response's `usage`, and the run's result carries the dollars (from
the provider's report or the price table, or unknown, never zero). `ParentOutcome.cost_usd` stays None because that field is for a figure the
harness reported; the usage is there for the benchmark runner to price.
"""
from __future__ import annotations

import json
import sys

from .. import providers
from ..usage import Usage
from .base import Detection, ParentCaps, ParentCommand, ParentOutcome, check_mode, kill_tree

NOTES = ("the model must support tool calls", "a gruntly command runs without a shell: no chaining, piping or redirection (a refused command is told why)")


def provider_setup(provider: str | None, model: str | None) -> tuple[str, str, str, str, dict[str, str]]:
    """(base URL, key variable name or '', provider name, model, environment) for a catalog provider. A provider and a model are both required."""
    if not provider:
        raise ValueError("the direct parent needs --provider (and --model): it has no login of its own; see `gruntly providers`")
    p = providers.ALL.get(provider)
    if p is None:
        raise ValueError(f"unknown provider {provider!r}; known: {', '.join(providers.ALL)}")
    env: dict[str, str] = {}
    key_env = ""
    if p.kind != "local":
        key = providers.api_key(p)
        if not key:
            raise ValueError(f"no API key for {p.name}: run `gruntly auth set {p.name}` (or set {p.key_env})")
        env[p.key_env] = key                                     # in the environment, never on the command line
        key_env = p.key_env
    use = model or p.default_model
    if not use:
        raise ValueError(f"provider {p.name} has no default model: pass --model ID (see `gruntly models {p.name}`)")
    return p.base_url, key_env, p.name, use, env


class DirectParent:
    name = "direct"

    def detect(self) -> Detection:
        return Detection(True, "built in")                       # nothing to install

    def command(self, task: str, mode: str, model: str | None = None, provider: str | None = None, structured: bool = False) -> ParentCommand:
        check_mode(mode)
        if mode != "delegating":
            raise ValueError("the direct parent only delegates: it has one tool, which runs gruntly commands; use a harness for --mode working")
        url, key_env, pname, use, env = provider_setup(provider, model)
        argv = [sys.executable, "-m", "gruntly.direct", "--base-url", url, "--model", use, "--provider", pname]
        if key_env:
            argv += ["--key-env", key_env]
        return ParentCommand(argv=argv, env=env, stdin=task, notes=list(NOTES))

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParentOutcome:
        data = None
        for line in reversed((stdout or "").strip().splitlines()):
            try:
                data = json.loads(line)
                break
            except ValueError:
                continue
        if not isinstance(data, dict):
            return ParentOutcome(final_message=((stderr or stdout or "").strip()[-600:] or "no output"), is_error=True)
        u = data.get("usage") or {}
        usage = Usage(prompt=int(u.get("prompt") or 0), completion=int(u.get("completion") or 0), cached=int(u.get("cached") or 0),
                      cache_write=int(u.get("cache_write") or 0), reasoning=int(u.get("reasoning") or 0), requests=int(u.get("requests") or 0),
                      missing=int(u.get("missing") or 0), cost_usd=u.get("cost_usd"))
        return ParentOutcome(final_message=str(data.get("final_message") or ""), is_error=bool(data.get("is_error")) or exit_code != 0,
                             usage=usage if usage.requests else None, turns=data.get("turns"))

    def capabilities(self) -> ParentCaps:
        return ParentCaps(replace_system_prompt=True, restrict_tools=True, restrict_shell=True, disable_extensions=True, reports_usage=True,
                          reports_cost=False, modes=("delegating",), notes=NOTES)

    def cancel(self, proc) -> None:
        kill_tree(proc)
