"""Child time budgets that grow with how slow this child really is, instead of one constant for every machine and model.

A fixed 600 s step budget killed a slow hosted child mid-work once. gruntly already records every run (harness, model, wall time,
requests) in the run index, so after a few runs of one child the budgets follow its own history:

  budget_s       1.5 x the 90th percentile of its recent wall times, at most 1800 s
  no_progress_s  3 x its median seconds per model request, at most 300 s

Budgets only ever grow past the defaults (900 s a run, 600 s a supervised step, 120 s idle): the history leaves out the runs that
hit a budget and the small tasks it is made of are lighter than a supervised step, so it underestimates exactly the slow cases.
A fast child keeps the defaults (stuck children are caught by the idle limit; wall time is not the cost that matters here).
Fewer than MIN_RUNS runs on record, or a value the person set themselves in their config: nothing changes.
"""
from __future__ import annotations

import statistics
from pathlib import Path

from . import store
from .spec import DEFAULTS, _merge, _toml, global_config_path

MIN_RUNS = 8        # runs of this child needed before its history means anything
WINDOW = 20         # the most recent ones count
BUDGET_CAP = 1800
IDLE_CAP = 300


def sized(harness: str, model: str | None, rows: list[dict] | None = None, budget_floor: int | None = None,
          idle_floor: int | None = None) -> dict:
    """{budget_s, no_progress_s} from the child's own history, never below the floors; empty when there is not enough of it."""
    budget_floor = DEFAULTS["budget_s"] if budget_floor is None else budget_floor
    idle_floor = DEFAULTS["no_progress_s"] if idle_floor is None else idle_floor
    rows = store.read_index() if rows is None else rows
    sel = [r for r in rows if r.get("harness") == harness and r.get("model") == model
           and r.get("status") in ("passed", "escalate") and (r.get("wall_s") or 0) > 0][-WINDOW:]
    if len(sel) < MIN_RUNS:
        return {}
    walls = sorted(r["wall_s"] for r in sel)
    p90 = walls[min(len(walls) - 1, int(0.9 * len(walls)))]
    out = {"budget_s": int(min(BUDGET_CAP, max(budget_floor, 1.5 * p90)))}
    per_request = [r["wall_s"] / r["child_usage"]["requests"] for r in sel
                   if (r.get("child_usage") or {}).get("requests")]
    if len(per_request) >= MIN_RUNS:
        out["no_progress_s"] = int(min(IDLE_CAP, max(idle_floor, 3 * statistics.median(per_request))))
    return out


def for_project(root: Path, harness: str, model: str | None, rows: list[dict] | None = None,
                budget_floor: int | None = None) -> dict:
    """`sized`, minus whatever the person set to a non-default value in their own config (their word wins)."""
    cfg = _merge(_toml(global_config_path()), _toml(Path(root) / ".gruntly.toml"))
    return {k: v for k, v in sized(harness, model, rows, budget_floor).items() if cfg.get(k, DEFAULTS[k]) == DEFAULTS[k]}
