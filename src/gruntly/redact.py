"""Secret redaction for everything stored or returned to the parent."""
from __future__ import annotations

import re

PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]
SENSITIVE_NAME = re.compile(r"(?i)(key|token|secret|passw|credential)")
MARK = "[REDACTED]"


def secrets_from_env(env: dict[str, str]) -> list[str]:
    """Values of sensitive-looking variables that were passed to the child."""
    return [v for k, v in env.items() if SENSITIVE_NAME.search(k) and len(v) >= 6]


def redact(text: str, secrets: list[str] | None = None) -> str:
    for s in sorted(secrets or [], key=len, reverse=True):
        if s:
            text = text.replace(s, MARK)
    for p in PATTERNS:
        text = p.sub(MARK, text)
    return text
