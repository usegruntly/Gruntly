"""Generates docs/where-delegation-wins.md: where handing work to a cheaper child beats the parent doing it alone, and where it does not.

  python bench/gold_doc.py                      # reads the sources listed below, writes docs/where-delegation-wins.md

Every number comes from stored rows (the files named in SOURCES); nothing is typed by hand. The verdict rule below was written before
any verdict was computed, and it is printed in the document. Three roles are compared per workload, on the same tasks:
  reference   the parent (Sonnet) doing the task itself
  delegated   the same parent handing it to the child (Haiku) through gruntly
  cheap       the child's model doing the task itself: what the cheapest option scores
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import cost_model as cm  # noqa: E402
import decision_report as dr  # noqa: E402
from cost_report import boot_ci  # noqa: E402

D = "docs/benchmarks/"
# (file, arm in that file, role, workload: a fixed name, or "row" to read it from the row, or "bucket" to map the code buckets)
SOURCES = [
    (D + "agent-pilot.json", "alone", "reference", "row"), (D + "agent-pilot.json", "forced", "delegated", "row"),
    (D + "agent-pilot.json", "haiku_alone", "cheap", "row"),
    (D + "agent-mixed.json", "alone", "reference", "mixed_research_then_code"), (D + "agent-mixed.json", "forced", "delegated", "mixed_research_then_code"),
    (D + "agent-mixed-haiku.json", "alone", "cheap", "mixed_research_then_code"),
    (D + "benchmark-cost.json", "alone", "reference", "bucket"), (D + "benchmark-cost-large.json", "alone", "reference", "bucket"),
    (D + "benchmark-real-alone.json", "alone", "reference", "bucket"),
    (D + "benchmark-claude-child-synth.json", "forced", "delegated", "bucket"), (D + "benchmark-real-claude-child.json", "forced", "delegated", "bucket"),
    (D + "benchmark-haiku-alone.json", "alone", "cheap", "bucket"), (D + "benchmark-real-haiku-alone.json", "alone", "cheap", "bucket"),
]
BUCKET_NAME = {"S": "code_edit_small", "L": "code_edit_larger", "R": "code_real_fix"}
TITLE = {
    "code_edit_small": ("Small code edits", "One file, a failing test, a clear request."),
    "code_edit_larger": ("Larger code edits", "Several bugs in several files, a 15-file rename, a CLI feature."),
    "code_real_fix": ("Real bug fixes in a public library", "One-line changelog statements; hidden tests ask for specifics. 8 fixes in `click`."),
    "code_reading": ("Reading code and answering", "Questions about a pinned source tree; ground truth from the syntax tree."),
    "exact_fetch": ("Exact fetch from a page", "Details of RFCs published after the models' training."),
    "web_research": ("Web research with sources", "Facts to find, every claim cited with a quote that must occur on the cited page."),
    "summarise": ("Summarising long inputs", "A 270 KB log and a 300-release changelog with planted facts."),
    "data_wrangle": ("Data wrangling by script", "A 5,000-row CSV and a 4,000-line event log; computed answers."),
    "mixed_research_then_code": ("Mixed: read the RFC, then code", "Implement a header parser whose details are only in an RFC."),
    "memorised_control": ("Control: answerable from memory", "A famous RFC's opcode list: needs no retrieval."),
}
ORDER = ["code_edit_small", "code_edit_larger", "code_real_fix", "code_reading", "exact_fetch", "web_research", "summarise", "data_wrangle",
         "mixed_research_then_code", "memorised_control"]

RULE = """**Verdict rule (fixed before any verdict was computed).** For a workload with n tasks (the tasks the delegated arm ran):
quality is *non-inferior* when the delegated pass rate is at least the reference's minus 1/n (it may lose at most one task);
*fresh-session saving* is the paired per-task cost difference of delegated against the reference with the one-off cold-cache cost removed;
*long-session saving* is modelled from the measured turns and child cost with the per-turn costs of a 150k to 300k context
(`bench/cost_model.py`), per correct task.
- **DELEGATE**: n is at least 4, quality is non-inferior, the fresh saving is at least 15% and its 95% interval is below zero.
- **DELEGATE IN LONG SESSIONS**: n is at least 4, quality is non-inferior, the fresh difference is within plus or minus 15%, and the modelled long-session saving is at least 25%.
- **AVOID**: delegated loses more than one task against the reference, or costs 15% or more *more* in fresh sessions with no modelled long-session saving of 25%.
- **UNSURE**: everything else, always including n below 4. UNSURE means: do not delegate by default, and run more tasks."""


def mean(xs):
    xs = list(xs)
    return statistics.fmean(xs) if xs else 0.0


def load_rows() -> dict[str, dict[str, list[dict]]]:
    out: dict[str, dict[str, list[dict]]] = {}
    seen_files = {}
    for path, arm, role, wl in SOURCES:
        f = ROOT / path
        if not f.exists():
            continue
        rows = seen_files.setdefault(path, json.loads(f.read_text(encoding="utf8")))
        for r in rows:
            if r.get("arm") != arm:
                continue
            name = r.get("workload") if wl == "row" else BUCKET_NAME.get(r.get("bucket")) if wl == "bucket" else wl
            if not name:
                continue
            r = {**r, "_file": path}
            out.setdefault(name, {}).setdefault(role, []).append(r)
    return out


def cold_adjusted(rows: list[dict]) -> list[float]:
    ref = dr.warm_reference(rows)
    return [dr.total(r) - dr.cold_extra(r, ref) for r in rows]


def analyse(groups: dict[str, list[dict]]) -> dict | None:
    dl, rf, ch = groups.get("delegated", []), groups.get("reference", []), groups.get("cheap", [])
    if not dl:
        return None
    tasks = sorted({r["task"] for r in dl})
    rf, ch = [r for r in rf if r["task"] in tasks], [r for r in ch if r["task"] in tasks]
    n = len(tasks)
    p = lambda rows: mean([1.0 if r["passed"] else 0.0 for r in rows]) if rows else None
    dl_cost = dict(zip(map(id, dl), cold_adjusted(dl)))
    rf_cost = dict(zip(map(id, rf), cold_adjusted(rf)))
    diffs, per_ref = [], []
    for t in tasks:
        a = [dl_cost[id(r)] for r in dl if r["task"] == t]
        b = [rf_cost[id(r)] for r in rf if r["task"] == t]
        if a and b:
            diffs.append(mean(a) - mean(b))
            per_ref.append(mean(b))
    ref_mean = mean(per_ref)
    fresh = mean(diffs) / ref_mean if ref_mean else None
    lo, hi = boot_ci(diffs) if len(diffs) >= 3 else (float("nan"), float("nan"))
    ci_rel = (lo / ref_mean, hi / ref_mean) if ref_mean and diffs and len(diffs) >= 3 else None
    # long session, modelled: measured turns and child cost, per-turn cost of a 150k to 300k context
    regime = "150-300k"
    a_turns, d_turns = max(1, round(mean([r.get("turns") or 0 for r in rf]))) if rf else None, max(1, round(mean([r.get("turns") or 0 for r in dl])))
    child = mean([r.get("child_cost_usd") or 0 for r in dl])
    alone_long = cm.alone(regime, a_turns) if a_turns else None
    deleg_long = cm.REGIMES[regime] * d_turns + child
    pd_, pr_ = p(dl), p(rf)
    per_correct = lambda cost, pr: (cost / pr) if pr else None
    long_saving = None
    if alone_long and pr_ and pd_:
        long_saving = per_correct(deleg_long, pd_) / per_correct(alone_long, pr_) - 1
    elif alone_long and pr_ and not pd_:
        long_saving = float("inf")
    non_inf = pr_ is not None and pd_ >= pr_ - 1 / n - 1e-9
    if n < 4:
        verdict = "UNSURE (n < 4)"
    elif pr_ is None:
        verdict = "UNSURE (no reference)"
    elif not non_inf and (pr_ - pd_) > 1 / n + 1e-9:
        verdict = "AVOID"
    elif non_inf and fresh is not None and fresh <= -0.15 and ci_rel and ci_rel[1] < 0:
        verdict = "DELEGATE"
    elif non_inf and fresh is not None and abs(fresh) <= 0.15 and long_saving is not None and long_saving <= -0.25:
        verdict = "DELEGATE IN LONG SESSIONS (modelled, not measured)"
    elif fresh is not None and fresh >= 0.15 and not (long_saving is not None and long_saving <= -0.25):
        verdict = "AVOID"
    else:
        verdict = "UNSURE"
    runs = len(dl)
    return {"tasks": tasks, "n": n, "runs": runs, "pass_d": pd_, "pass_r": pr_, "pass_c": p(ch), "cost_d": mean(dl_cost.values()),
            "cost_r": mean(rf_cost.values()) if rf else None, "cost_c": mean([dr.total(r) for r in ch]) if ch else None,
            "child_d": child, "fresh": fresh, "ci": ci_rel, "long": long_saving, "turns_r": a_turns, "turns_d": d_turns,
            "kb_r": mean([r.get("tool_output_bytes", 0) / 1024 for r in rf]) if rf else None,
            "kb_d": mean([r.get("tool_output_bytes", 0) / 1024 for r in dl]), "verdict": verdict, "non_inferior": non_inf,
            "dl": dl, "rf": rf, "ch": ch, "wall_d": mean([r["wall_s"] for r in dl]), "wall_r": mean([r["wall_s"] for r in rf]) if rf else None}


def pct(x, digits=0):
    return "-" if x is None else ("n/a" if x == float("inf") else f"{x:+.{digits}%}")


def money(x):
    return "-" if x is None else f"${x:.3f}"


def calibration(data) -> list[str]:
    pts = [(r["parent_confidence"] / 100.0, 1.0 if r["passed"] else 0.0, r["task"]) for w in data.values() for r in w["dl"] if r.get("parent_confidence") is not None]
    L = ["## What the parent said it expected, and what happened", "",
         "In the delegated arm the parent wrote `CONFIDENCE: NN%` before handing the work over. It is recorded, never used to decide anything.", ""]
    if not pts:
        return L + ["No confidence values recorded yet.", ""]
    L += ["| stated chance | runs | passed | pass rate |", "|---|---|---|---|"]
    for lo, hi, name in ((0, 0.5, "below 50%"), (0.5, 0.8, "50% to 79%"), (0.8, 1.01, "80% or more")):
        sel = [o for c, o, _ in pts if lo <= c < hi]
        L.append(f"| {name} | {len(sel)} | {int(sum(sel))} | {('%.0f%%' % (100 * mean(sel))) if sel else '-'} |")
    brier = mean([(c - o) ** 2 for c, o, _ in pts])
    base = mean([o for _, o, _ in pts])
    L += ["", f"Brier score {brier:.3f} over {len(pts)} runs (always saying the overall pass rate of {base:.0%} would score {mean([(base - o) ** 2 for _, o, _ in pts]):.3f}; lower is better; "
          "a score no better than that means the stated chance carries no information).", ""]
    return L


def build() -> str:
    rows = load_rows()
    data = {w: a for w in ORDER if w in rows and (a := analyse(rows[w]))}
    metas = []
    for m in sorted((ROOT / "docs/benchmarks").glob("*.meta.json")):
        try:
            metas += json.loads(m.read_text(encoding="utf8"))
        except ValueError:
            pass
    claude = sorted({e.get("claude") for e in metas if e.get("claude")})
    L = ["# Where delegation wins, and where it does not", "",
         f"*Generated {time.strftime('%Y-%m-%d')} by `bench/gold_doc.py` from stored benchmark rows. Do not edit by hand: change the sources and regenerate.*", "",
         "The question: for each kind of agent work, does a dearer parent (Claude Sonnet) handing the work to a cheaper child (Claude Haiku, through gruntly) "
         "reach the parent's result for less money? Costs are API-equivalent dollars as Claude Code reports them: the parent's session plus the child's own "
         "dollars. The child is never counted as free. Claude Code versions in these runs: " + (", ".join(claude) or "unknown") + ".", "",
         "## How to read the evidence", "",
         "- **Measured** numbers are from runs in fresh benchmark sessions, one run per task and arm unless a row says otherwise. With a handful of tasks the intervals are wide.",
         "- **Modelled** numbers (marked) extend measured turns and child cost to a long session with the per-turn costs measured in real sessions. They are not runs.",
         "- **Pilot** means fewer than 4 tasks: the verdict is UNSURE by rule, whatever the numbers look like.",
         "- A workload where the reference or the cheap model does as well for less is reported with the same prominence as one where delegation wins.", "", RULE, "",
         "## Verdict matrix", "",
         "| workload | tasks | pass: parent alone | pass: delegated | pass: child alone | $ per run: parent alone | $ per run: delegated | $ per run: child alone | fresh-session change | modelled long-session change, per correct task | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for w, a in data.items():
        ci = f" ({a['ci'][0]:+.0%} to {a['ci'][1]:+.0%})" if a["ci"] else ""
        L.append(f"| {TITLE[w][0]} | {a['n']} | {pct(a['pass_r'])[1:] if a['pass_r'] is not None else '-'} | {pct(a['pass_d'])[1:]} | "
                 f"{(pct(a['pass_c'])[1:]) if a['pass_c'] is not None else '-'} | {money(a['cost_r'])} | {money(a['cost_d'])} | {money(a['cost_c'])} | "
                 f"{pct(a['fresh'])}{ci} | {pct(a['long'])} | **{a['verdict']}** |")
    L += ["", "Pass rates are shares of runs whose answer or patch met the task's grader (hidden tests, or the deterministic graders in `bench/graders.py`). "
          "\"Fresh-session change\" is delegated against the parent alone, paired by task, with the one-off cold-cache cost removed.", ""]
    L += ["## What delegation does to the parent's context", "",
          "The mechanism the saving relies on: whatever the child reads stays out of the parent's context, which the parent pays to re-read on every turn.", "",
          "| workload | parent tool output kept in its context, alone | delegated | parent turns, alone | delegated | wall seconds, alone | delegated |", "|---|---|---|---|---|---|---|"]
    for w, a in data.items():
        L.append(f"| {TITLE[w][0]} | {('%.1f KB' % a['kb_r']) if a['kb_r'] is not None else '-'} | {a['kb_d']:.1f} KB | {a['turns_r'] or '-'} | {a['turns_d']} | "
                 f"{('%.0f' % a['wall_r']) if a['wall_r'] is not None else '-'} | {a['wall_d']:.0f} |")
    L.append("")
    L += calibration(data)
    L += ["## By workload", ""]
    for w, a in data.items():
        title, what = TITLE[w]
        L += [f"### {title}", "", f"*{what}* Tasks: {', '.join('`%s`' % t for t in a['tasks'])}. Verdict: **{a['verdict']}**.", "",
              "| task | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said | what went wrong |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for role, rows_ in (("parent alone", a["rf"]), ("delegated", a["dl"]), ("child alone", a["ch"])):
            for r in sorted(rows_, key=lambda r: r["task"]):
                g = r.get("grade") or {}
                why = "-"
                if not r["passed"]:
                    bits = [f"missing: {g['facts_missing']}" if g.get("facts_missing") else "", f"{g.get('citations', 0) - g.get('citations_valid', 0)} invalid citations" if g.get("citations") and g.get("citations") != g.get("citations_valid") else "",
                            f"wrong: {g['wrong'][:2]}" if g.get("wrong") else "", f"missing lines: {g['missing'][:3]}" if g.get("missing") else "",
                            f"extra lines: {g['extra'][:3]}" if g.get("extra") else "", (r.get("judge") or {}).get("failed", [""])[0][:60] if r.get("judge", {}).get("failed") else ""]
                    why = "; ".join(b for b in bits if b)[:150] or "failed"
                sc = r.get("score")
                L.append(f"| {r['task']} | {role} | {('%.2f' % sc) if sc is not None else ('1.00' if r['passed'] else '0.00')} | {'yes' if r['passed'] else 'NO'} | {dr.total(r):.3f} | "
                         f"{dr.parent_usd(r):.3f} | {r.get('child_cost_usd') or 0:.4f} | {r.get('turns')} | {r['wall_s']} | "
                         f"{('%d%%' % r['parent_confidence']) if r.get('parent_confidence') is not None else '-'} | {why} |")
        L.append("")
    L += ["## Method and reproducibility", "",
          "- Tasks: `bench/tasks/` (code, with hidden tests), `bench/tasks-real/` (fix commits of public repositories) and `bench/tasks-agent/` (non-code). `bench/make_agent_tasks.py` regenerates the non-code ones deterministically; their ground truth comes from generation, the syntax tree, or immutable web pages published after the models' training.",
          "- Graders: `bench/graders.py`. No model judges anything. Research answers must cite a quote that occurs on the cited page.",
          "- Runners: `bench/run_bench.py` (code), `bench/run_agent_bench.py` (non-code). Per-run raw material (transcripts, gruntly records, answers, final patches) is in the git-ignored `bench/runs*/` folders.",
          "- Reports for one experiment: `bench/decision_report.py`. This document: `bench/gold_doc.py`.", "",
          "## Limits of this evidence", "",
          "- One repetition per task and arm in most rows: no run-to-run variance is measured.",
          "- Reference and child-alone rows for the code workloads come from earlier days; their cache warmth and prompts may differ.",
          "- Fresh sessions understate what the parent pays per turn in a long session; the long-session column is a model.",
          "- The Haiku child's results do not carry over to a local model or another hosted model; each needs its own run.",
          "- Subjective work (writing, design) and side-effecting work (setup, deployment) are not measured yet, so this document says nothing about them."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    out = ROOT / "docs" / "where-delegation-wins.md"
    out.write_text(build(), encoding="utf8")
    print(f"wrote {out}")
