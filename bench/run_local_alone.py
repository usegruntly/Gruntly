"""The local model ALONE on the benchmark tasks: no Claude and no gruntly (no gates, no retry loop, no evaluate & fix).

It is the analogue of the `alone` arm: the stock OpenCode agent works directly in the repo with the same instructions
Claude gets ("do the work yourself and run the check"), then the task's hidden tests judge the result. Costs no paid
tokens. Also records whether the visible check passes at the end, to show how often the model's own "done" is right.

  python bench/run_local_alone.py --tasks flatten,paginate --reps 2 --out docs/benchmarks/benchmark-local-alone.md
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from run_bench import judge, prepare, prompt_for, sh  # noqa: E402
from gruntly.adapters.base import scrub_env  # noqa: E402
from gruntly.adapters.opencode import OpenCodeAdapter  # noqa: E402
from gruntly.spec import build_spec  # noqa: E402


def run_one(task_dir: Path, rep: int, a) -> dict:
    with tempfile.TemporaryDirectory(prefix="local-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp) / "repo"
        spec = prepare(task_dir, work, "opencode", a.model)
        prompt = prompt_for("alone", spec)
        task = build_spec({"brief": "x", "acceptance": spec["acceptance"], "harness": "opencode", "model": a.model})
        cmd = OpenCodeAdapter().command(task, work, prompt, None, profile=None)   # the stock agent, no slim profile
        t0 = time.time()
        err = None
        try:
            p = subprocess.run(cmd.argv, cwd=str(work), input=cmd.stdin, env=scrub_env(cmd.env), capture_output=True,
                               text=True, encoding="utf8", errors="replace", timeout=a.timeout_s)
            out = OpenCodeAdapter().parse(p.stdout, p.stderr, p.returncode)
        except subprocess.TimeoutExpired:
            out, err = None, f"timeout after {a.timeout_s}s"
        wall = round(time.time() - t0)
        visible = sh(spec["acceptance"][0]["cmd"].replace("python ", f'"{sys.executable}" ', 1), work, shell=True).returncode == 0
        usage = (out.usage if out else {}) or {}
        return {"task": task_dir.name, "rep": rep, "hidden_pass": judge(task_dir, work), "visible_pass": visible, "wall_s": wall,
                "child_tokens": usage.get("total_tokens") or 0, "requests": usage.get("requests") or 0,
                "input_per_request": usage.get("input_per_request"), "error": err,
                "final_message": (out.final_message if out else "")[:200]}


def report(rows: list[dict], meta: dict) -> str:
    mean = statistics.fmean
    n = len(rows)
    L = ["# The local model alone (no Claude, no gruntly)", "",
         f"`opencode` stock agent / `{meta['model']}`, run {time.strftime('%Y-%m-%d')}. Same tasks, instructions and hidden-test judge as the "
         "`alone` arm for Claude. No gates, no retries, no evaluate & fix.", "",
         "| task | hidden-test pass | visible check passes at the end | wall s | child tokens | requests |", "|---|---|---|---|---|---|"]
    for t in sorted({r["task"] for r in rows}):
        x = [r for r in rows if r["task"] == t]
        L.append(f"| {t} | {sum(r['hidden_pass'] for r in x)}/{len(x)} | {sum(r['visible_pass'] for r in x)}/{len(x)} | "
                 f"{mean(r['wall_s'] for r in x):.0f} | {mean(r['child_tokens'] for r in x):.0f} | {mean(r['requests'] for r in x):.1f} |")
    claims = [r for r in rows if r["visible_pass"]]
    L += ["", f"**Overall: {sum(r['hidden_pass'] for r in rows)}/{n} pass the hidden tests; {len(claims)}/{n} pass the visible check, "
          f"and {sum(1 for r in claims if not r['hidden_pass'])} of those fail the hidden tests (false passes).** "
          f"Mean wall time {mean(r['wall_s'] for r in rows):.0f} s, mean {mean(r['child_tokens'] for r in rows):,.0f} local tokens per run."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen/qwen3.5-9b")
    ap.add_argument("--tasks", default="")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--timeout-s", type=int, default=900)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--out", default=str(HERE.parent / "docs" / "benchmarks" / "benchmark-local-alone.md"))
    a = ap.parse_args()
    names = [n for n in a.tasks.split(",") if n] or sorted(p.name for p in (HERE / "tasks").iterdir() if p.is_dir())
    raw = Path(a.out).with_suffix(".json")
    rows = json.loads(raw.read_text(encoding="utf8")) if raw.exists() and a.resume else []
    done = {(r["task"], r["rep"]) for r in rows}
    for rep in range(1, a.reps + 1):
        for n in names:
            if (n, rep) in done:
                continue
            print(f"[{n} / rep {rep}] ...", flush=True)
            r = run_one(HERE / "tasks" / n, rep, a)
            rows.append(r)
            print(f"  hidden={r['hidden_pass']} visible={r['visible_pass']} wall={r['wall_s']}s tokens={r['child_tokens']} {r['error'] or ''}", flush=True)
            raw.write_text(json.dumps(rows, indent=1), encoding="utf8")
            Path(a.out).write_text(report(rows, vars(a)), encoding="utf8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
