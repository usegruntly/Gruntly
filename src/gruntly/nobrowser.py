"""Nothing gruntly starts unattended may open a browser tab.

Aider asks "Open URL for more info?" at several points (the release notes on the first run of a version, the token-limits page when a
context window overflows, every URL in a provider's error text) and `--yes-always`, which gruntly needs so that Aider never waits for a person,
answers yes to each of them. Aider has no switch to refuse, so each such run opened a tab: a fresh `HOME` (every test of the real binary, any
run with a private folder) counts as the first run of a version again, and a loop of failing calls on a small context window opened the token-limits page
each time. Found 2026-11-13, after the tabs had filled the machine's memory.

Python's `webbrowser` (which Aider uses) tries the program named in `BROWSER` before any real browser, so a launched harness gets a `BROWSER`
that runs a program which does nothing and succeeds. Set `GRUNTLY_ALLOW_BROWSER=1` to leave the variable alone (a harness that has to sign in
through a browser).
"""
from __future__ import annotations

import os
import sys

ALLOW = "GRUNTLY_ALLOW_BROWSER"


def command(argv: list[str] | None = None) -> str:
    """A `BROWSER` value that runs `argv` (default: the running Python, doing nothing) with the URL as its last argument. `webbrowser` splits the
    value like a shell would, so every part is quoted and written with forward slashes (a backslash would be taken as an escape)."""
    argv = argv or [sys.executable, "-c", "pass"]
    return " ".join(f'"{a.replace(chr(92), "/")}"' for a in argv) + " %s"


def env(argv: list[str] | None = None) -> dict[str, str]:
    """The environment to add to a harness launched without a person watching: empty when the caller has allowed browsers."""
    if os.environ.get(ALLOW):
        return {}
    return {"BROWSER": command(argv)}
