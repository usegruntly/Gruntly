"""Does a persistent child session (ACP) matter? The rule was fixed before the lean-agent rerun (see docs/decisions.md):

  (a) >= 25% of runs sent a real steering follow-up (`--continue` after a run that PASSED, not after an error or refusal), AND
  (b) those follow-ups took >= 30% of the run's agent-run time (the child re-reading what it already knew).

  python bench/persistence_check.py docs/benchmarks/benchmark-lean2.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def calls(path: Path) -> list[dict]:
    """agent-run calls in order: {continue, status, secs}."""
    uses: dict[str, dict] = {}
    order: list[str] = []
    for ln in path.read_text(encoding="utf8").splitlines():
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        m = e.get("message")
        blocks = m.get("content") if isinstance(m, dict) and isinstance(m.get("content"), list) else []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and isinstance(b.get("input"), dict):
                cmd = b["input"].get("command", "")
                if cmd.startswith("gruntly agent-run"):
                    uses[b["id"]] = {"continue": "--continue" in cmd, "status": "?", "secs": 0.0}
                    order.append(b["id"])
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in uses:
                x = b.get("content")
                x = x if isinstance(x, str) else json.dumps(x)
                st = next((ln.split(":", 1)[1].strip().split()[0] for ln in x.splitlines() if ln.startswith("status:")), "?")
                uses[b["tool_use_id"]]["status"] = st
        if e.get("type") == "tool_progress" and e.get("tool_use_id") in uses:
            u = uses[e["tool_use_id"]]
            u["secs"] = max(u["secs"], float(e.get("elapsed_time_seconds") or 0))
    return [uses[i] for i in order]


def main() -> None:
    rows = json.loads(Path(sys.argv[1]).read_text(encoding="utf8"))
    steered = total = 0
    follow_s = all_s = 0.0
    for r in rows:
        if r["arm"] != "lean":
            continue
        cs = calls(HERE / "runs" / f"{r['task']}.{r['arm']}.{r['rep']}.jsonl")
        total += 1
        all_s += sum(c["secs"] for c in cs)
        real = [c for prev, c in zip(cs, cs[1:]) if c["continue"] and prev["status"] == "passed"]
        steered += bool(real)
        follow_s += sum(c["secs"] for c in real)
    share_runs = steered / total if total else 0
    share_time = follow_s / all_s if all_s else 0
    verdict = share_runs >= 0.25 and share_time >= 0.30
    print(f"runs {total}; with a real steering follow-up {steered} ({share_runs:.0%}); "
          f"follow-up time {follow_s:.0f}s of {all_s:.0f}s ({share_time:.0%})")
    print("PERSISTENCE MATTERS" if verdict else "persistence does not matter by the pre-registered rule")


if __name__ == "__main__":
    main()
