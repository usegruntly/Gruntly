"""Small checks used as the acceptance command when a project has no tests for the kind of change being made.

    python -m gruntly.checks changed FILE [FILE ...]     passes when every file differs from the run's starting point

A "changed" pass proves only that the child did edit the named files; the parent still has to read the diff.
"""
from __future__ import annotations

import subprocess
import sys


def changed(paths: list[str]) -> int:
    missing = []
    for p in paths:
        # Against HEAD (the run's starting commit), not the index: gruntly stages the child's edits before it runs the checks,
        # and an edit that is already staged would read as "no change" against the index.
        tracked_diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", p]).returncode == 1
        new_file = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", p],
                                  capture_output=True, text=True).stdout.strip() != ""
        if not (tracked_diff or new_file):
            missing.append(p)
    if missing:
        print("not changed yet: " + ", ".join(missing))
        return 1
    print("changed: " + ", ".join(paths))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "changed":
        return changed(argv[1:])
    print("usage: python -m gruntly.checks changed FILE [FILE ...]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
