"""The numbers a decision needs, from the rows `run_bench.py` writes: does a cheap child (Claude Haiku) behind a dearer parent
(Sonnet) get close to the parent's result for much less money?

  python bench/decision_report.py --run "sonnet>haiku=docs/benchmarks/benchmark-claude-child-synth.json" \
      --baseline "sonnet-alone=docs/benchmarks/benchmark-cost.json::alone" --baseline "haiku-alone=docs/benchmarks/benchmark-haiku-alone.json::alone" \
      --out docs/benchmarks/decision-claude-child.md

--run LABEL=FILE[::ARM]       rows of the delegated arm(s) being judged (repeat for more)
--baseline LABEL=FILE[::ARM]  rows to compare against; the FIRST baseline is the paired reference (usually the parent alone), the
                              others are shown beside it (usually the child alone: the ceiling of what the child can do)
Every figure is computed from the stored rows, so it can be recomputed; nothing is typed in by hand.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import cost_model as cm          # noqa: E402
from cost_report import boot_ci   # noqa: E402

WRITE, READ = 4.0e-6, 0.10e-6    # Sonnet 5.5, 1-hour cache write and cache read, $ per token


def mean(xs):
    xs = list(xs)
    return statistics.fmean(xs) if xs else 0.0


def wilson(k: int, n: int) -> str:
    if not n:
        return "-"
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return f"{k}/{n} ({100 * max(c - h, 0):.0f}-{100 * min(c + h, 1):.0f}%)"


def load(spec: str) -> tuple[str, list[dict]]:
    label, _, rest = spec.partition("=")
    path, _, arm = rest.partition("::")
    rows = json.loads(Path(path).read_text(encoding="utf8"))
    rows = [r for r in rows if not arm or r.get("arm") == arm]
    for r in rows:
        r["_label"] = label
    return label, rows


def parent_usd(r):
    return r.get("cost_usd") or 0.0


def total(r):
    return parent_usd(r) + (r.get("child_cost_usd") or 0) + (r.get("reviewer_cost_usd") or 0)


def warm_reference(rows):
    """Median first-call cache read and write of the runs that started warm: what a cold start should have cost."""
    w = [r["first_call"] for r in rows if r.get("first_call") and not r.get("cold_start")]
    if not w:
        return None
    return statistics.median(f["cache_read"] for f in w), statistics.median(f["cache_write"] for f in w)


def cold_extra(r, ref):
    """Dollars a cold start added: its first call wrote the whole prefix instead of reading most of it. Sonnet sessions only."""
    if not r.get("cold_start") or not ref or "sonnet" not in "".join((r.get("model_usage") or {})):
        return 0.0
    fc = r["first_call"]
    return max(fc["cache_write"] * WRITE - (ref[1] * WRITE + ref[0] * READ), 0.0)


def bucket_of(rs):
    return sorted({r.get("bucket", "?") for r in rs})


def status_of(r):
    g = r.get("gruntly") or []
    return g[-1]["status"] if g else None


def child_did_all(r):
    """The child's patch is what shipped: gruntly passed and applied it and the parent made no edit afterwards."""
    g = r.get("gruntly") or []
    return bool(g) and g[-1].get("status") == "passed" and bool(g[-1].get("applied")) and not r.get("takeover_edits")


def summary_table(label, rows, base_rows, ref_all):
    L = []
    for b in ("S", "L", "R"):
        rs = [r for r in rows if r.get("bucket") == b]
        if not rs:
            continue
        ref = warm_reference(rows)
        adj = [total(r) - cold_extra(r, ref) for r in rs]
        paired, dp, paired_raw = [], [], []
        for r in rs:
            same = [total(x) for x in base_rows if x["task"] == r["task"]]
            if same:
                paired.append(total(r) - cold_extra(r, ref) - mean(same))       # warm-to-warm: the cold start is not the arm's doing
                paired_raw.append(total(r) - mean(same))
                dp.append(mean(same))
        k = sum(1 for r in rs if r["passed"])
        fp = sum(1 for r in rs if not r["passed"] and any(g.get("status") == "passed" for g in (r.get("gruntly") or [])))
        cases = [(r["judge"]["cases_passed"], r["judge"]["cases_passed"] + r["judge"]["cases_failed"] + r["judge"].get("cases_error", 0))
                 for r in rs if r.get("judge")]
        cs = f"{sum(a for a, _ in cases)}/{sum(t for _, t in cases)}" if cases else "-"
        d = (f"{mean(paired):+.3f} ({mean(paired) / mean(dp):+.0%}), CI {boot_ci(paired)[0]:+.3f}..{boot_ci(paired)[1]:+.3f}, cheaper in "
             f"{sum(1 for x in paired if x < 0)}/{len(paired)}; with cold start {mean(paired_raw):+.3f}"
             if paired and len(paired) > 1 else (f"{mean(paired):+.3f}" if paired else "-"))
        cost_pass = f"{mean([total(r) for r in rs]) / (k / len(rs)):.3f}" if k else "inf"
        L.append(f"| {label} | {b} | {wilson(k, len(rs))} | {cs} | {fp or '-'} | {mean([total(r) for r in rs]):.3f} | {mean([parent_usd(r) for r in rs]):.3f} | "
                 f"{mean([r.get('child_cost_usd') or 0 for r in rs]):.4f} | {mean(adj):.3f} | {cost_pass} | {d} | "
                 f"{mean([r.get('turns') or 0 for r in rs]):.1f} | {mean([r['wall_s'] for r in rs]):.0f} |")
    return L


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", default=[])
    ap.add_argument("--baseline", action="append", default=[])
    ap.add_argument("--out")
    a = ap.parse_args()
    def merged(specs):               # the same label given twice (a small-task file and a large-task file) is one arm
        out: dict[str, list[dict]] = {}
        for s in specs:
            label, rows = load(s)
            out.setdefault(label, []).extend(rows)
        return list(out.items())
    runs = merged(a.run)
    bases = merged(a.baseline)
    mine = {r["task"] for _, rows in runs for r in rows}          # compare like with like: only the tasks the delegated arms ran
    bases = [(label, [r for r in rows if r["task"] in mine]) for label, rows in bases]
    ref_label, ref_rows = bases[0] if bases else ("-", [])
    L = ["# Decision report: a cheap child behind a dearer parent", "",
         "Generated by `bench/decision_report.py` from stored rows; every number below can be recomputed from them. Costs are API-equivalent "
         "dollars as Claude Code reports them (parent `total_cost_usd`, plus the child's own `total_cost_usd` per attempt, plus any reviewer). "
         f"Reference for pairing: **{ref_label}**. Paired differences are per task (delegated run minus the baseline's mean for the same task), "
         "with a 95% bootstrap interval; with few tasks the intervals are wide and a difference that does not clear zero is not a finding.", ""]
    L += ["## 1. Does it get close to the parent for less money?", "",
          "| arm | bucket | pass (95% interval) | hidden cases passed | false passes | total $/run | parent $ | child $ | total $ without cold start | $ per correct task | paired difference vs reference, warm ($ per run) | parent turns | wall s |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for label, rows in bases:
        L += summary_table(label, rows, ref_rows if label != ref_label else [], None)
    for label, rows in runs:
        L += summary_table(label, rows, ref_rows, None)
    L += ["", "False pass = gruntly said `passed` but the hidden tests failed. Cold start = the session's first call read nothing from the prompt cache "
              "and wrote its whole prefix (about $0.10 for this plugin setup); it depends on when the previous run was, not on the arm, so the "
              "column without it is the fairer one across arms run on different days.", ""]

    L += ["## 2. Is the child doing the work? (delegated arms)", "",
          "| arm | bucket | delegated | child shipped the patch, parent edited nothing | passed on child's first attempt | mean gruntly attempts | parent follow-ups (`--continue`) | `gruntly wait` calls | child tool calls / parent tool calls | child share of dollars | child wall s | parent wall s |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for label, rows in runs:
        for b in ("S", "L", "R"):
            rs = [r for r in rows if r.get("bucket") == b]
            if not rs:
                continue
            deleg = [r for r in rs if r.get("gruntly")]
            ptools = [sum((r.get("tools") or {}).values()) for r in rs]
            ctools = []
            for r in rs:
                n = 0
                for g in r.get("gruntly") or []:
                    m = re.search(r"(\d+) tool calls", g.get("child_trace") or "")
                    n += int(m.group(1)) if m else 0
                ctools.append(n)
            tot_d = sum(total(r) for r in rs)
            L.append(f"| {label} | {b} | {len(deleg)}/{len(rs)} | {sum(1 for r in rs if child_did_all(r))}/{len(rs)} | "
                     f"{sum(1 for r in rs if (r.get('gruntly') or [{}])[0].get('status') == 'passed' and (r.get('gruntly') or [{}])[0].get('attempts') == 1)}/{len(rs)} | "
                     f"{mean([(g.get('attempts') or 0) for r in deleg for g in r['gruntly']]):.1f} | "
                     f"{sum((r.get('gruntly_calls') or {}).get('continue', 0) for r in rs)} | {sum((r.get('gruntly_calls') or {}).get('wait', 0) for r in rs)} | "
                     f"{sum(ctools)}/{sum(ptools)} | {sum(r.get('child_cost_usd') or 0 for r in rs) / tot_d:.0%} | "
                     f"{mean([r.get('gruntly_wall_s') or 0 for r in rs]):.0f} | {mean([r.get('parent_wall_s') or 0 for r in rs]):.0f} |")

    L += ["", "## 3. Quality against the references (paired by task)", "",
          "| arm | compared with | both pass | only delegated passes | only the reference passes | neither |", "|---|---|---|---|---|---|"]
    for label, rows in runs:
        for blabel, brows in bases:
            both = onlyd = onlyb = neither = 0
            for t in sorted({r["task"] for r in rows}):
                d = [r["passed"] for r in rows if r["task"] == t]
                bb = [r["passed"] for r in brows if r["task"] == t]
                if not bb:
                    continue
                dp, bp = mean(d) >= 0.5, mean(bb) >= 0.5
                both += dp and bp
                onlyd += dp and not bp
                onlyb += bp and not dp
                neither += not dp and not bp
            if both + onlyd + onlyb + neither:
                L.append(f"| {label} | {blabel} | {both} | {onlyd} | {onlyb} | {neither} |")

    L += ["", "## 4. Where the parent's money goes (delegated arms, Sonnet prices)", "",
          "| arm | uncached input | cache read | cache write | output | of which cold-start excess | parent turns | parent output tokens |", "|---|---|---|---|---|---|---|---|"]
    for label, rows in runs:
        ref = warm_reference(rows)
        mu = [m for r in rows for m in [r.get("model_usage") or {}] if m]
        if not mu:
            continue
        def part(key, price):
            return sum((v.get(key) or 0) * price for m in mu for v in m.values())
        n = len(rows)
        L.append(f"| {label} | ${part('input', 2e-6) / n:.4f} | ${part('cache_read', READ) / n:.4f} | ${part('cache_write', WRITE) / n:.4f} | "
                 f"${part('output', 10e-6) / n:.4f} | ${sum(cold_extra(r, ref) for r in rows) / n:.4f} | "
                 f"{mean([r.get('turns') or 0 for r in rows]):.1f} | {mean([(r.get('tokens') or {}).get('output', 0) for r in rows]):.0f} |")

    L += ["", "## 5. What this would cost in a real session (model, not a measurement)", "",
          "The benchmark sessions are fresh, so the parent's per-turn cost is small. In a real session each parent turn re-reads a large cached "
          "context, which is where delegation should win. This table feeds the measured parent turns, child cost and failure rate into "
          "`bench/cost_model.py` (per-turn costs measured from real sessions; see `docs/investigation-2026-11-11.md`).", "",
          "| arm | bucket | regime | alone (modelled, same turns as the reference) | delegated (modelled) | difference |", "|---|---|---|---|---|---|"]
    for label, rows in runs:
        for b in ("S", "L", "R"):
            rs = [r for r in rows if r.get("bucket") == b]
            bs = [x for x in ref_rows if x.get("bucket") == b]
            if not rs or not bs:
                continue
            alone_turns = max(1, round(mean([x.get("turns") or 0 for x in bs])))
            child = mean([r.get("child_cost_usd") or 0 for r in rs])
            fail = mean([0 if child_did_all(r) else 1 for r in rs])
            for regime in cm.REGIMES:
                al = cm.alone(regime, alone_turns)
                de = cm.delegated(regime, 2, child=child, takeover_p=fail, alone_turns=alone_turns)
                L.append(f"| {label} | {b} | {regime} | ${al:.3f} ({alone_turns} turns) | ${de:.3f} (2 turns, child ${child:.3f}, takeover {fail:.0%}) | {de / al - 1:+.0%} |")

    L += ["", "## 6. Every run", "",
          "| task | arm | pass | hidden cases (pass/fail) | total $ | parent $ | child $ | cold | parent turns | wall s (child / parent) | gruntly: status, attempts | why it failed, if it did | final patch (+/-) |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for label, rows in bases + runs:
        for r in sorted(rows, key=lambda x: (x.get("bucket", ""), x["task"])):
            g = r.get("gruntly") or []
            j = r.get("judge") or {}
            fp = r.get("final_patch") or {}
            why = "; ".join(f"{x.get('status')}: {x.get('reason') or ','.join(x.get('failed_gates') or []) or '-'}" for x in g if x.get("status") != "passed") or \
                  ("false pass: " + ", ".join(j.get("failed", [])[:3]) if (g and not r["passed"]) else "-")
            L.append(f"| {r['task']} | {label} | {'yes' if r['passed'] else 'NO'} | {j.get('cases_passed', '-')}/{j.get('cases_failed', '-')} | {total(r):.3f} | "
                     f"{parent_usd(r):.3f} | {r.get('child_cost_usd') or 0:.4f} | {'cold' if r.get('cold_start') else ''} | {r.get('turns')} | "
                     f"{r.get('gruntly_wall_s', '-')} / {r.get('parent_wall_s', '-')} | "
                     f"{', '.join(f'{x.get('status')} x{x.get('attempts')}' for x in g) or '-'} | {why[:120]} | "
                     f"{('+%s/-%s' % (fp.get('lines_added'), fp.get('lines_removed'))) if fp else '-'} |")

    L += ["", "## 7. Limits of this evidence", "",
          "- One repetition per task and arm: no run-to-run variance is measured. Differences smaller than the intervals above are noise.",
          "- Baselines may come from earlier days; their cache warmth, plugin version and prompts can differ. The cold-start column removes the biggest known effect.",
          "- Fresh sessions understate what a parent pays per turn in a long session; section 5 is a model built from measured per-turn costs.",
          "- Tasks are small, public and chosen with known hidden tests; they say little about design work or vague requests.",
          "- Hidden-test case counts show partial correctness, but a fix that fails any case is counted as a fail."]
    text = "\n".join(L) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf8")
        print(f"wrote {a.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
