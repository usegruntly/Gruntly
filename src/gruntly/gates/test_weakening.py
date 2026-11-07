"""Heuristic: existing tests must not be deleted, edited, skipped or stripped of assertions."""
from __future__ import annotations

import re
from pathlib import Path

from .. import worktree as wtmod
from . import matches_any

TEST_PATTERNS = ["tests/**", "test/**", "**/tests/**", "**/test/**", "**/__tests__/**",
                 "test_*.py", "*_test.py", "*.test.*", "*.spec.*", "*_test.go"]
ASSERT = re.compile(r"\bassert\b|\bexpect\s*\(|\bassert[A-Z_]\w*\s*\(|\bt\.(?:Error|Fatal)")
SKIP = re.compile(r"pytest\.mark\.(?:skip|xfail)|pytest\.skip|\bxfail\b|@unittest\.skip|\bt\.Skip|"
                  r"\b(?:it|test|describe)\.(?:skip|todo)\b|\bxit\s*\(|\bxdescribe\s*\(")


def is_test_file(path: str) -> bool:
    return matches_any(path, TEST_PATTERNS)


def check(spec, wt: Path, base: str) -> dict:
    if spec.tests_writable:
        return {"ok": True, "findings": []}
    findings: list[str] = []
    for path, st in wtmod.name_status(wt, base).items():
        if not is_test_file(path):
            continue
        if st == "D":
            findings.append(f"deleted test file: {path}")
        elif st == "M":
            removed = added = 0
            skipped = False
            for line in wtmod.patch(wt, base, [path]).splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    added += bool(ASSERT.search(line))
                    skipped = skipped or bool(SKIP.search(line))
                elif line.startswith("-") and not line.startswith("---"):
                    removed += bool(ASSERT.search(line))
            if skipped:
                findings.append(f"skip/xfail added in: {path}")
            if removed > added:
                findings.append(f"assertions removed in: {path} ({removed} removed, {added} added)")
            if not skipped and removed <= added:
                findings.append(f"existing test edited: {path}")
    return {"ok": not findings, "findings": findings[:20]}
