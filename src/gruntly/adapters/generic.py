"""Escape hatch: any command template with {prompt}, {workdir}, {model} and {endpoint}, plain-text output. The endpoint gruntly gives every child is also
passed in the environment as OPENAI_BASE_URL and OPENAI_API_BASE, with OPENAI_API_KEY (the proxy's placeholder for a hosted provider, never the real key)."""
from __future__ import annotations

import os
import shlex
from pathlib import Path

from .base import Caps, ChildOutcome, Command, Detection, count_malformed, kill_tree


class GenericAdapter:
    name = "generic"

    def detect(self) -> Detection:
        return Detection(True, None, "any command template")

    def command(self, task, workdir: Path, prompt: str, resume: str | None) -> Command:
        tpl = task.child_cmd
        parts = list(tpl) if isinstance(tpl, (list, tuple)) else shlex.split(str(tpl), posix=(os.name != "nt"))
        endpoint = getattr(task, "endpoint", "") or ""
        subs = {"prompt": prompt, "workdir": str(workdir), "model": task.model or "", "endpoint": endpoint}
        argv = []
        for p in parts:
            for k, v in subs.items():
                p = p.replace("{" + k + "}", v)
            argv.append(p)
        env = {"GRUNTLY_WORKDIR": str(workdir)}
        if endpoint:        # the OpenAI-compatible endpoint gruntly gives every child (the local server, or the proxy of a hosted provider), as most tools expect it
            env.update({"OPENAI_BASE_URL": endpoint, "OPENAI_API_BASE": endpoint, "OPENAI_API_KEY": getattr(task, "api_key", "") or "local"})
        return Command(argv=argv, env=env, stdin=None)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome:
        return ChildOutcome(final_message=stdout.strip(), is_error=exit_code != 0,
                            malformed_calls=count_malformed(stdout, stderr))

    def capabilities(self) -> Caps:
        return Caps()

    def cancel(self, proc) -> None:
        kill_tree(proc)
