"""Escape hatch: any command template with {prompt}, {workdir} and {model}, plain-text output."""
from __future__ import annotations

import os
import shlex
from pathlib import Path

from .base import Caps, ChildOutcome, Command, Detection, count_malformed, kill_tree


class GenericAdapter:
    name = "generic"

    def detect(self) -> Detection:
        return Detection(True, None, "any command template")

    def command(self, task, workdir: Path, prompt: str, resume: str | None, profile=None) -> Command:
        tpl = task.child_cmd
        parts = list(tpl) if isinstance(tpl, (list, tuple)) else shlex.split(str(tpl), posix=(os.name != "nt"))
        subs = {"prompt": prompt, "workdir": str(workdir), "model": task.model or ""}
        argv = []
        for p in parts:
            for k, v in subs.items():
                p = p.replace("{" + k + "}", v)
            argv.append(p)
        return Command(argv=argv, env={"GRUNTLY_WORKDIR": str(workdir)}, stdin=None)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome:
        return ChildOutcome(final_message=stdout.strip(), is_error=exit_code != 0,
                            malformed_calls=count_malformed(stdout, stderr))

    def capabilities(self) -> Caps:
        return Caps()

    def cancel(self, proc) -> None:
        kill_tree(proc)
