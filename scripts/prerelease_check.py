#!/usr/bin/env python
"""Fail if the repository holds something that should not be public: a key-shaped string, a real person's home path, a real email address.

usage: python scripts/prerelease_check.py [--history] [--words WORD,WORD]

By default it scans the files git tracks. `--history` also checks every commit's author and committer email, which is what a public repository shows to the world.
Words you do not want anywhere (your name, a username) come from `--words` or the GRUNTLY_PRERELEASE_WORDS environment variable, so they never need to be written
into the repository. Matches are reported as file:line and a kind; the matched text of a key is never printed. Exit 1 when anything is found.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

KEY = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|nvapi-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}"
                 r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
FAKE_KEY = re.compile(r"(?i)test|fake|dummy|example|wrong|abcd|secret|xyz|placeholder|1234")          # tokens that tests plant on purpose
HOME = re.compile(r"(?:[A-Za-z]:[\\/]+Users[\\/]+|(?<![\w.-])/Users/|(?<![\w.-])/home/)([A-Za-z0-9._-]+)")      # C:\Users\x, C:\\Users\\x (JSON), /Users/x, /home/x
GENERIC_HOME = {"user", "users", "username", "you", "name", "me", "runner", "public", "default", "all", "x", "u", "test", "tester", "someone", "yourname", "example"}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})\b")        # a domain ends in letters: `Gruntly@v0.3.0` is a version, not an address
FINE_MAIL_DOMAINS = re.compile(r"(?i)(^|\.)(example\.(com|org|test)|users\.noreply\.github\.com|localhost|invalid|anthropic\.com|github\.com|python\.org|pypi\.org)$")
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2", ".pdf", ".zip", ".gz", ".whl"}


def tracked(root: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, encoding="utf8", errors="replace").stdout
    return [root / p for p in out.split("\0") if p]


def scan_text(rel: str, text: str, words: list[str]) -> list[str]:
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in KEY.finditer(line):
            if not FAKE_KEY.search(m.group(0)):
                found.append(f"{rel}:{n}: key-shaped string")
        for m in HOME.finditer(line):
            if m.group(1).lower() not in GENERIC_HOME:
                found.append(f"{rel}:{n}: a real person's home path")
        for m in EMAIL.finditer(line):
            if not FINE_MAIL_DOMAINS.search(m.group(1)) and len(m.group(1)) > 5:
                found.append(f"{rel}:{n}: an email address")
        low = line.lower()
        for w in words:
            if w and w.lower() in low:
                found.append(f"{rel}:{n}: the word {w!r}")
    return found


def scan_tree(root: Path, words: list[str]) -> list[str]:
    found = []
    for p in tracked(root):
        if p.suffix.lower() in SKIP_SUFFIX or not p.is_file():
            continue
        try:
            text = p.read_bytes().decode("utf8")
        except UnicodeDecodeError:
            continue
        found += scan_text(p.relative_to(root).as_posix(), text, words)
    return found


def scan_history(root: Path) -> list[str]:
    out = subprocess.run(["git", "log", "--all", "--format=%ae%n%ce"], cwd=root, capture_output=True, text=True, encoding="utf8").stdout
    bad = {e for e in out.split() if "@" in e and not FINE_MAIL_DOMAINS.search(e.split("@", 1)[1])}
    return [f"git history: {len(bad)} author/committer email address(es) that are not a noreply address (rewrite with a mailmap or filter-repo before publishing)"] if bad else []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--history", action="store_true", help="also check commit author and committer emails")
    ap.add_argument("--words", default="", help="comma-separated words to forbid anywhere (also GRUNTLY_PRERELEASE_WORDS)")
    ap.add_argument("--root", default=".", help="the repository (default: the current folder)")
    a = ap.parse_args(argv)
    words = [w.strip() for w in (a.words + "," + os.environ.get("GRUNTLY_PRERELEASE_WORDS", "")).split(",") if w.strip()]
    root = Path(a.root).resolve()
    found = scan_tree(root, words) + (scan_history(root) if a.history else [])
    for f in found:
        print(f)
    print(f"prerelease check: {'FOUND ' + str(len(found)) + ' problem(s)' if found else 'clean'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
