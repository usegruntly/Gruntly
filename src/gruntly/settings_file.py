"""Edit top-level keys of a gruntly TOML settings file (`.gruntly.toml`, `~/.config/gruntly/config.toml`) without disturbing
the rest of it: comments, tables and other keys stay as they are. Only simple values are written (strings, numbers, booleans).
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v))            # a JSON string is a valid TOML basic string


def set_values(path: Path, values: dict) -> None:
    """Set each key to its value; a value of None removes the key. Keys live above the first [table]."""
    lines = path.read_text(encoding="utf8").splitlines() if path.is_file() else []
    cut = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("[")), len(lines))
    head, tail = lines[:cut], lines[cut:]
    for key, val in values.items():
        pat = re.compile(rf"^\s*{re.escape(key)}\s*=")
        idx = next((i for i, ln in enumerate(head) if pat.match(ln)), None)
        if val is None:
            if idx is not None:
                del head[idx]
            continue
        new = f"{key} = {_fmt(val)}"
        if idx is not None:
            head[idx] = new
        else:
            at = len(head)
            while at > 0 and not head[at - 1].strip():      # keep trailing blank lines after the new key
                at -= 1
            head.insert(at, new)
    out = head + ([""] if head and tail and head[-1].strip() else []) + tail
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf8")


def get_value(path: Path, key: str):
    import tomllib
    try:
        return tomllib.loads(path.read_text(encoding="utf8")).get(key)
    except (OSError, tomllib.TOMLDecodeError):
        return None
