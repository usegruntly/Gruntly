"""`agent-run --review`: one review of a finished run, by the parent's model, outside the parent's session.

The parent pays two turns for a delegation however long it takes. A review that happens inside gruntly's call costs a
fraction of one more parent turn (Sonnet at low effort, caching off, about $0.007 on a 2k-token diff) and carries only what it
needs: the person's rules, the project's CLAUDE.md / AGENTS.md, the request, the diff and the child's own report. When the
reviewer finds something wrong the same call sends it back to the child once, with the reviewer's words, and reviews again:
the parent reads one block with both verdicts. A FIX that stands after that is reported as such; it never changes a pass the
gates gave (a reviewer may add red to the report, never turn a failed gate green).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import rules as rulesmod, supervise
from .redact import redact

DIFF_CHARS = 8_000
REPORT_CHARS = 2_000
ASK = ("Judge whether this change does the whole request correctly and completely. Check what the small model may have "
       "missed: validation and error types, empty and boundary inputs, not mutating arguments, names and metadata kept, other "
       "places the change must reach, and claims in its report that the diff does not show. Do not ask for style changes, "
       "renames or tests. Reply APPROVE: one line saying what the change does; or FIX: exactly what is wrong or missing and "
       "what to do (a small model will do it, so be concrete).")


def system_text(root: Path, request: str) -> str:
    """The part that never changes between the reviews of one request: who you are, the rules, the project files, the task."""
    return supervise.REVIEWER_SYSTEM + "\n\n" + supervise.context(root, {"request": request, "check": None})


def system_file(root: Path, text: str) -> Path:
    """The system prompt as a file whose name is its hash: the same text is always the same bytes at the same path."""
    d = Path(root) / ".gruntly" / "review"
    d.mkdir(parents=True, exist_ok=True)
    f = d / (hashlib.sha1(text.encode("utf8")).hexdigest()[:12] + ".txt")
    if not f.is_file():
        f.write_text(text, encoding="utf8")
    return f


def message(patch: str, report: str, tests: str) -> str:
    return (f"RESULT: {tests}\n\nDIFF (written by the small model):\n{redact(patch, [])[:DIFF_CHARS] or '(no change)'}\n\n"
            f"THE SMALL MODEL'S REPORT (verify it against the diff):\n{redact(report, [])[-REPORT_CHARS:] or '(no report)'}\n\n{ASK}")


def review(root: Path, request: str, patch: str, report: str, tests: str, model: str, call=None) -> tuple[str, str, float]:
    """(APPROVE | FIX, the reviewer's words, cost in USD). `call` is the reviewer; tests swap it."""
    call = call or supervise.reviewer_call
    reply, cost = call(message(patch, report, tests), model, system_file=system_file(root, system_text(root, request)), cache=False)
    kind, rest = supervise.verdict(reply)
    return ("APPROVE" if kind == "APPROVE" else "FIX"), " ".join(rest.split())[:700], cost
