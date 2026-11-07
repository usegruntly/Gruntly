"""Gates: deterministic checks that gruntly runs itself after the child stops."""
from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        out += "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)
        i += 1
    return re.compile(out + r"\Z")


def glob_match(path: str, pattern: str) -> bool:
    """gitignore-ish: patterns without a slash match the basename at any depth."""
    path = path.replace("\\", "/")
    if "/" not in pattern.rstrip("/"):
        return bool(_compile(pattern).match(path.rsplit("/", 1)[-1]))
    return bool(_compile(pattern.lstrip("/")).match(path))


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(glob_match(path, p) for p in patterns)
