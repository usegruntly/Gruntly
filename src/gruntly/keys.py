"""API keys for hosted providers, kept in a user-level file: ~/.config/gruntly/keys.toml (GRUNTLY_CONFIG_DIR moves it).

Lookup order: the provider's environment variable first (CI, one-off overrides), then this file. The file is plain text,
so it is created readable by its owner only (chmod 600; on Windows the inherited permissions are removed and only the current
user is granted access). Keys are never read from a project file, never written to a run's spec or logs, and never printed.
"""
from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path


def keys_path() -> Path:
    from .spec import global_config_path
    return global_config_path().parent / "keys.toml"


def _load() -> dict:
    p = keys_path()
    try:
        return dict(tomllib.loads(p.read_text(encoding="utf8")).get("keys", {}))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _lock_down(p: Path) -> bool:
    """Owner-only access. True only if it was applied (the caller must not claim it otherwise)."""
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME")
            exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "icacls.exe"
            if not user or not exe.is_file():
                return False
            r = subprocess.run([str(exe), str(p), "/inheritance:r", "/grant:r", f"{user}:(R,W)"],
                               capture_output=True, timeout=15)
            return r.returncode == 0
        os.chmod(p, 0o600)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _save(keys: dict) -> bool:
    p = keys_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "[keys]\n" + "".join(f"{k} = {json.dumps(v)}\n" for k, v in sorted(keys.items()))
    p.write_text("", encoding="utf8") if not p.exists() else None
    locked = _lock_down(p)             # restrict first, then write the secret
    p.write_text(body, encoding="utf8")
    return locked


INVISIBLE = "﻿​‌‍⁠ "     # BOM, zero-width and non-breaking spaces: pasting or piping on Windows adds them


def clean(key: str) -> str:
    """A key as the provider issued it: without whitespace and without the invisible characters that come along with a paste
    or a Windows pipe (a leading BOM made every request fail with a header or auth error)."""
    return (key or "").replace("\r", "").replace("\n", "").translate({ord(c): None for c in INVISIBLE}).strip()


def lookup(provider: str, env_var: str) -> tuple[str | None, str | None]:
    """(key, where it came from): 'environment' or 'keys file'."""
    v = clean(os.environ.get(env_var, ""))
    if v:
        return v, "environment"
    v = clean(_load().get(provider, ""))
    return (v, "keys file") if v else (None, None)


def set_key(provider: str, key: str) -> bool:
    """Returns whether the file could be restricted to its owner. Raises ValueError for a key that cannot be one."""
    key = clean(key)
    if not key:
        raise ValueError("the key is empty")
    if not key.isascii() or any(c.isspace() for c in key):
        raise ValueError("the key contains spaces or characters that are not plain ASCII: copy it again from the provider's page")
    keys = _load()
    keys[provider] = key
    return _save(keys)


def remove(provider: str) -> bool:
    keys = _load()
    if provider not in keys:
        return False
    del keys[provider]
    _save(keys)
    return True


def stored() -> list[str]:
    return sorted(_load())
