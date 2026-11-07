"""OpenCode adapter. Unverified: Milestone 3 replaces this with fixtures from a real install."""
from __future__ import annotations

from pathlib import Path

from .base import Caps, ChildOutcome, Command, Detection, count_malformed, kill_tree, which


class OpenCodeAdapter:
    name = "opencode"

    def detect(self) -> Detection:
        if not which("opencode"):
            return Detection(False, None, "opencode not on PATH")
        return Detection(True, None, "installed; adapter not yet verified against real output")

    def command(self, task, workdir: Path, prompt: str, resume: str | None) -> Command:
        argv = [which("opencode") or "opencode", "run"]
        if task.model:
            argv += ["--model", task.model]
        if resume:
            argv += ["--session", resume]
        return Command(argv=argv, env={}, stdin=prompt)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome:
        return ChildOutcome(final_message=stdout.strip()[-2000:], is_error=exit_code != 0,
                            malformed_calls=count_malformed(stdout, stderr))

    def capabilities(self) -> Caps:
        return Caps()

    def cancel(self, proc) -> None:
        kill_tree(proc)
