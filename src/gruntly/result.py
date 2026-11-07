"""The compact result contract. Hard cap ~6000 chars; tails cut from the front, summaries from the back."""
from __future__ import annotations

import json

SCHEMA_VERSION = 1
MAX_CHARS = 6000
SUMMARY_CHARS = 600
BUNDLE_LINES = 60


def tail_lines(text: str, n: int, max_chars: int = 2500) -> str:
    out = "\n".join(text.strip().splitlines()[-n:])
    return out if len(out) <= max_chars else "…" + out[-max_chars:]


def head_chars(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def size(result: dict) -> int:
    return len(json.dumps(result, ensure_ascii=False))


def enforce_cap(result: dict, cap: int = MAX_CHARS) -> dict:
    """Shrink the largest free-text fields until the result fits."""
    steps = [
        lambda r: _shrink_bundle(r, 30),
        lambda r: _shrink_tails(r, 1200),
        lambda r: r.__setitem__("child_summary", head_chars(r.get("child_summary", ""), 300)),
        lambda r: _shrink_bundle(r, 15),
        lambda r: _shrink_tails(r, 400),
        lambda r: _drop_attempts(r),
        lambda r: r.__setitem__("child_summary", head_chars(r.get("child_summary", ""), 100)),
        lambda r: _shrink_bundle(r, 5),
        lambda r: _shrink_tails(r, 100),
    ]
    for step in steps:
        if size(result) <= cap:
            break
        step(result)
    return result


def _shrink_bundle(r: dict, lines: int) -> None:
    b = r.get("failure_bundle")
    if b and b.get("output"):
        b["output"] = tail_lines(b["output"], lines, max_chars=lines * 80)


def _shrink_tails(r: dict, chars: int) -> None:
    for g in r.get("gates", {}).values():
        if isinstance(g, dict) and g.get("tail"):
            g["tail"] = "…" + g["tail"][-chars:] if len(g["tail"]) > chars else g["tail"]
    b = r.get("failure_bundle")
    if b and len(b.get("output", "")) > chars:
        b["output"] = "…" + b["output"][-chars:]


def _drop_attempts(r: dict) -> None:
    b = r.get("failure_bundle")
    if b:
        b["attempts"] = b.get("attempts", [])[-2:]


def build(*, run_id: str, status: str, attempts: int, gates: dict, diff_stat: dict, child_summary: str,
          failure_bundle: dict | None, timing: dict, child_usage: dict, next_cmds: list[str],
          error: str | None = None) -> dict:
    r = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": status,
        "attempts": attempts,
        "gates": gates,
        "diff_stat": diff_stat,
        "child_summary": "UNTRUSTED. " + head_chars(child_summary, SUMMARY_CHARS),
        "failure_bundle": failure_bundle,
        "timing": timing,
        "child_usage": child_usage,
        "next": next_cmds,
    }
    if error:
        r["error"] = head_chars(error, 400)
    return enforce_cap(r)
