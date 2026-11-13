"""The stand-in child of `gruntly demo`: a few lines of Python that play a coding agent, so the demo needs no model, no key and no network.

usage: python -m gruntly.demo_child <scenario> [prompt]   (runs in the worktree, like any child)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXED = "def add(a, b):\n    return a + b\n"
WEAKENED = "from calc import add\n\n\ndef test_add():\n    assert True\n\n\nif __name__ == \"__main__\":\n    test_add()\n    print(\"ok\")\n"


def main_checkout() -> Path:
    """The checkout this worktree came from: a worktree's `.git` file names it, which is how a real model sometimes ends up editing it (issue #6)."""
    common = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True).stdout.strip()
    return Path(common).resolve().parent


def main(argv: list[str]) -> int:
    scenario = argv[0] if argv else "fix"
    if scenario == "fix":
        Path("calc.py").write_text(FIXED)
        print("fixed add() in calc.py")
    elif scenario == "weaken":                        # the tempting shortcut: make the test pass instead of the code
        Path("test_calc.py").write_text(WEAKENED)
        print("all tests pass now")
    elif scenario == "leak":                          # right fix, wrong place for one extra file
        Path("calc.py").write_text(FIXED)
        (main_checkout() / "notes.txt").write_text("written into the original checkout, not the worktree\n")
        print("fixed add() and left my notes")
    else:
        print(f"unknown scenario {scenario!r}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
