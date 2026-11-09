"""Cost comparison from the rows `run_bench.py` writes: does delegating through gruntly save paid cost?

  python bench/cost_report.py docs/benchmarks/benchmark-cost.json [--out docs/benchmarks/benchmark-cost-summary.md]

Primary number: the parent's own cost (Claude Code's `total_cost_usd`, whole session, takeovers included) with the child at zero.
Reference numbers: raw token counts, and what the totals would be if the child's tokens were paid at a stated price
(Sonnet 5.5 input, $2.00 per million, and Haiku 5.5 input, $0.10 per million: first-party list prices cached 2026-10-06).
Child tokens are priced as input tokens, which slightly understates a paid child (output tokens cost more).
Comparisons are paired by (task, repetition), matching a gruntly arm against its own baseline:
  policy vs alone        the plugin as a user has it, against Claude Code as shipped
  lean vs lean_alone     a stripped-down Claude directing gruntly, against the same stripped-down Claude working alone
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

PRICE = {"sonnet-5.5 input": 2.00, "haiku-5.5 input": 0.10}      # $ per million tokens
PAIRS = [("policy", "alone"), ("lean", "lean_alone"), ("lean", "alone"), ("forced", "alone")]


def parent_tokens(r: dict) -> int:
    t = r["tokens"]
    return t["input"] + t["cache_write"] + t["cache_read"] + t["output"]


def mean(xs):
    return statistics.fmean(xs) if xs else 0.0


def boot_ci(diffs: list[float], n: int = 4000, seed: int = 7) -> tuple[float, float]:
    if len(diffs) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    ms = sorted(mean([rng.choice(diffs) for _ in diffs]) for _ in range(n))
    return ms[int(0.025 * n)], ms[int(0.975 * n)]


def child_cost(r: dict, price: float) -> float:
    return (r.get("child_tokens") or 0) * price / 1e6


def table(rows: list[dict]) -> list[str]:
    arms = [a for a in ("alone", "policy", "forced", "lean_alone", "lean") if any(r["arm"] == a for r in rows)]
    L = ["| arm | runs | passed | parent $/run | $ per correct task | turns | parent tokens (all kinds) | of which output | child tokens | delegated | false pass |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in arms:
        rs = [r for r in rows if r["arm"] == a]
        ok = sum(r["passed"] for r in rs)
        tot = sum(r["cost_usd"] for r in rs)
        L.append(f"| {a} | {len(rs)} | {ok}/{len(rs)} | {mean([r['cost_usd'] for r in rs]):.4f} | {tot / ok if ok else float('nan'):.4f} | "
                 f"{mean([r['turns'] or 0 for r in rs]):.1f} | {mean([parent_tokens(r) for r in rs]):,.0f} | "
                 f"{mean([r['tokens']['output'] for r in rs]):,.0f} | {mean([r['child_tokens'] for r in rs]):,.0f} | "
                 f"{sum(1 for r in rs if r['gruntly_status'])}/{len(rs)} | {sum(1 for r in rs if not r['passed'] and 'passed' in r['gruntly_status']) or '-'} |")
    return L


def compare(rows: list[dict], arm: str, base: str) -> list[str]:
    by = {(r["task"], r["rep"], r["arm"]): r for r in rows}
    keys = sorted({(t, rep) for t, rep, a in by if a == arm and (t, rep, base) in by})
    if not keys:
        return []
    pairs = [(by[(t, rep, arm)], by[(t, rep, base)]) for t, rep in keys]
    L = [f"### {arm} against {base} ({len(pairs)} paired runs)", ""]
    d = [a["cost_usd"] - b["cost_usd"] for a, b in pairs]
    lo, hi = boot_ci(d)
    base_mean = mean([b["cost_usd"] for _, b in pairs])
    L.append(f"- **Primary (child free): parent cost per run {mean([a['cost_usd'] for a, _ in pairs]):.4f} vs {base_mean:.4f} "
             f"= {mean(d) / base_mean:+.0%}** (mean paired difference {mean(d):+.4f} $, 95% bootstrap interval {lo:+.4f} to {hi:+.4f}). "
             f"{sum(1 for x in d if x < 0)} of {len(d)} pairs cheaper with gruntly, {sum(1 for x in d if x > 0)} dearer.")
    pa, pb = [a["passed"] for a, _ in pairs], [b["passed"] for _, b in pairs]
    L.append(f"- Correct (hidden tests): {sum(pa)}/{len(pa)} with gruntly vs {sum(pb)}/{len(pb)} for the baseline.")
    ta, tb = mean([parent_tokens(a) for a, _ in pairs]), mean([parent_tokens(b) for _, b in pairs])
    L.append(f"- Parent tokens per run (all kinds, cache reads included): {ta:,.0f} vs {tb:,.0f} ({ta / tb - 1:+.0%}); output tokens "
             f"{mean([a['tokens']['output'] for a, _ in pairs]):,.0f} vs {mean([b['tokens']['output'] for _, b in pairs]):,.0f}.")
    ct = mean([a["child_tokens"] for a, _ in pairs])
    L.append(f"- Child tokens per run: {ct:,.0f}. In raw tokens, parent + child = {ta + ct:,.0f} vs {tb:,.0f} ({(ta + ct) / tb - 1:+.0%}).")
    for name, price in PRICE.items():
        tot_a = mean([a["cost_usd"] + child_cost(a, price) for a, _ in pairs])
        L.append(f"- If the child were paid at {name} (${price:.2f}/M): {tot_a:.4f} vs {base_mean:.4f} = {tot_a / base_mean - 1:+.0%}.")
    L.append("")
    L.append("| task | " + f"{arm} $ | {base} $ | difference | gruntly status |")
    L.append("|---|---|---|---|---|")
    for (t, rep), (a, b) in zip(keys, pairs):
        L.append(f"| {t}#{rep} | {a['cost_usd']:.4f} | {b['cost_usd']:.4f} | {a['cost_usd'] - b['cost_usd']:+.4f} | "
                 f"{', '.join(a['gruntly_status']) or '-'}{'' if a['passed'] else ' (FAILED hidden tests)'} |")
    L.append("")
    return L


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = json.loads(Path(a.rows).read_text(encoding="utf8"))
    L = [f"# Cost summary: {Path(a.rows).name}", "",
         f"{len(rows)} runs, {len({r['task'] for r in rows})} tasks. Parent cost is Claude Code's own `total_cost_usd` for the whole session "
         "(cache reads included, takeover after a failed delegation included). The child's tokens cost nothing in the primary numbers.", ""]
    L += table(rows) + [""]
    for arm, base in PAIRS:
        L += compare(rows, arm, base)
    text = "\n".join(L) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf8")
    print(text)


if __name__ == "__main__":
    main()
