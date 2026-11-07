"""Hermes Agent adapter. Unverified: Milestone 3 replaces this with fixtures from a real install."""
from __future__ import annotations

from pathlib import Path

from .base import Caps, ChildOutcome, Command, Detection, count_malformed, kill_tree, which


class HermesAdapter:
    name = "hermes"

    def detect(self) -> Detection:
        if not which("hermes"):
            return Detection(False, None, "hermes not on PATH")
        return Detection(True, None, "installed; adapter not yet verified against real output")

    def command(self, task, workdir: Path, prompt: str, resume: str | None) -> Command:
        argv = [which("hermes") or "hermes", "chat", "-Q", "-q", prompt]
        if task.model:
            argv += ["-m", task.model]
        return Command(argv=argv, env={}, stdin=None)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome:
        return ChildOutcome(final_message=stdout.strip()[-2000:], is_error=exit_code != 0,
                            malformed_calls=count_malformed(stdout, stderr))

    def capabilities(self) -> Caps:
        return Caps()

    def cancel(self, proc) -> None:
        kill_tree(proc)
