"""The compact result contract (schema 2).

A pass is ~250 bytes: status, files, line counts and whether it was applied. Anything the child wrote
(its summary, test output, handoff notes) lives under the single `untrusted` key, only on non-passes,
and is length-capped. Nothing child-written appears anywhere else, including `next`.
Hard cap ~6000 chars; tails are cut from the front, summaries from the back.
"""
from __future__ import annotations

import json

SCHEMA_VERSION = 2
MAX_CHARS = 6000
SUMMARY_CHARS = 300
BUNDLE_LINES = 20
GATE_TAIL_LINES = 60  # raw capture per gate before it is compacted


def tail_lines(text: str, n: int, max_chars: int = 2000) -> str:
    out = "\n".join(text.strip().splitlines()[-n:])
    return out if len(out) <= max_chars else "…" + out[-max_chars:]


def head_chars(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def size(result: dict) -> int:
    return len(json.dumps(result, ensure_ascii=False))


def compact_gates(gates: dict) -> dict:
    """Passing gates are `true`; failing ones keep their detail, minus raw command output."""
    out = {}
    for name, g in gates.items():
        if g.get("ok"):
            out[name] = True
        else:
            out[name] = {k: v for k, v in g.items() if k not in ("tail", "output")}
    return out


def enforce_cap(result: dict, cap: int = MAX_CHARS) -> dict:
    u = result.get("untrusted") or {}
    steps = [
        lambda: u.__setitem__("gate_output", tail_lines(u.get("gate_output", ""), 10, 800)) if "gate_output" in u else None,
        lambda: u.__setitem__("summary", head_chars(u.get("summary", ""), 100)) if "summary" in u else None,
        lambda: u.pop("handoff", None),
        lambda: result.get("failure_bundle", {}).__setitem__("attempts", result["failure_bundle"].get("attempts", [])[-2:])
        if result.get("failure_bundle") else None,
        lambda: u.pop("gate_output", None),
    ]
    for step in steps:
        if size(result) <= cap:
            break
        step()
    return result


def build(*, run_id: str, status: str, attempts: int, gates: dict, diff_stat: dict, failure_bundle: dict | None,
          wall_s: int, child_tokens: int | None, next_cmds: list[str], untrusted: dict | None = None,
          applied: bool | None = None, verify: str | None = None, review_hint: list[str] | None = None,
          warnings: list[str] | None = None, error: str | None = None,
          child_trace: str = "", child: dict | None = None, escalation: dict | None = None) -> dict:
    r: dict = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "status": status, "attempts": attempts}
    if applied is not None:
        r["applied"] = applied
    if verify:
        r["verify"] = verify
    r["gates"] = compact_gates(gates)
    r["diff_stat"] = {"files": diff_stat["files"], "insertions": diff_stat["insertions"],
                      "deletions": diff_stat["deletions"], "paths": diff_stat["paths"][:10]}
    if review_hint:
        r["review_hint"] = review_hint
    if warnings:
        r["warnings"] = warnings
    if child_trace:
        r["child_trace"] = child_trace
    if escalation:
        r["escalation"] = escalation     # why a failed run failed, and whether a stronger model should take it over
    if child:
        r["child"] = child
    if failure_bundle:
        r["failure_bundle"] = failure_bundle
    if untrusted:
        r["untrusted"] = untrusted
    if error:
        r["error"] = head_chars(error, 400)
    r["wall_s"] = wall_s
    if child_tokens:
        r["child_tokens"] = child_tokens
    r["next"] = next_cmds
    return enforce_cap(r)
