"""Benchmark the non-coding agent tasks (bench/tasks-agent/*): does handing the work to a cheaper child beat the parent doing it alone?

  python bench/run_agent_bench.py --arms alone,forced,haiku_alone --tasks fetch_rfc9110_4xx --out docs/benchmarks/agent-pilot.md

Arms (all with the same tools: the shell, file tools and WebSearch):
  alone        the parent model (--parent-model, Sonnet) does the task itself
  forced       the same parent with the gruntly plugin, told to state its chance of success and then delegate with `gruntly agent-run --ask`
  haiku_alone  Haiku does the task itself (the cheapest the child could ever be, and a difficulty probe)
Every answer is graded by `graders.py` (no model judge). Rows keep what `run_bench.py` keeps (cost split, turns, tool-output size, cold
start, gruntly records, artifacts) plus the grade, the parent's stated confidence and the child's raw answer.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import graders  # noqa: E402
import run_bench as rb  # noqa: E402

TASKS = HERE / "tasks-agent"
TOOLS = [*rb.TOOLS, "WebSearch"]
ARMS = ("alone", "forced", "haiku_alone")


def load(name: str) -> tuple[dict, Path]:
    d = TASKS / name
    return yaml.safe_load((d / "task.yaml").read_text(encoding="utf8")), d


def prepare(d: Path, work: Path, a) -> None:
    shutil.copytree(d / "work", work) if (d / "work").is_dir() and any((d / "work").iterdir()) else work.mkdir(parents=True)
    (work / ".gruntly.toml").write_text(
        f'harness = "{a.child_harness}"\nmodel = "{a.child_model}"\nbudget_s = {a.child_budget_s}\nno_progress_s = {a.child_idle_s}\nmax_attempts = 1\n', encoding="utf8")
    rb.sh(["git", "init", "-q", "-b", "main"], work)
    rb.sh(["git", "add", "-A"], work)
    rb.sh(["git", "-c", "user.name=b", "-c", "user.email=b@b", "commit", "-qm", "start"], work)


def prompt_for(arm: str, spec: dict, has_files: bool) -> str:
    body = spec["prompt"].strip() + "\n\nAnswer format: " + spec["format"].strip()
    where = "The task's files are in the current directory. " if has_files else ""
    if arm in ("alone", "haiku_alone"):
        return (body + f"\n\n{where}Do the work yourself with your tools (the shell can fetch pages, WebSearch can search). Reply with only the answer, "
                       "in exactly the format above.")
    return (body + "\n\nFirst write one line `CONFIDENCE: NN%` -- your estimate of the chance (0-100) that the child agent gets this exactly right. "
                   "Then delegate it through gruntly as your gruntly skill says for a question (one call: `gruntly agent-run --ask` with the question and "
                   "the answer format in plain words). Follow the skill's result rules. Reply with only the answer, in exactly the format above: copy the "
                   "child's answer unless you can see it is wrong, and drop anything the format does not ask for. If gruntly fails, do it yourself.")


def run_one(name: str, arm: str, rep: int, a) -> dict:
    spec, d = load(name)
    with tempfile.TemporaryDirectory(prefix="agentbench-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp) / "repo"
        prepare(d, work, a)
        model = "haiku" if arm == "haiku_alone" else a.parent_model
        cmd = [shutil.which("claude") or "claude", "-p", "--allowedTools", *TOOLS, "--output-format", "stream-json", "--verbose",
               "--max-turns", "40", "--max-budget-usd", str(a.budget_usd), "--model", model]
        if arm == "forced":
            cmd += ["--plugin-dir", str(rb.PLUGIN)]
        t0, err = time.time(), None
        try:
            p = rb.sh(cmd, work, timeout=max(2400, 2 * a.child_budget_s + 600), input=prompt_for(arm, spec, any(f.is_file() for f in work.rglob("*") if ".git" not in f.parts and f.name != ".gruntly.toml")))
            raw = p.stdout
            if not raw.strip():
                err = (p.stderr or "empty output")[-300:]
        except subprocess.TimeoutExpired:
            raw, err = "", "timeout"
        wall = round(time.time() - t0)
        runs_dir = HERE / (a.runs_dir or "runs-agent")
        runs_dir.mkdir(exist_ok=True)
        stem = f"{name}.{arm}.{rep}"
        (runs_dir / f"{stem}.jsonl").write_text(raw, encoding="utf8")
        info = rb.analyse(raw)
        answer = ""
        for line in raw.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "result":
                answer = e.get("result") or ""
        grade = graders.grade(spec, answer)
        conf = None
        for m in re.finditer(r"CONFIDENCE:\s*(\d+)\s*%", raw):
            conf = int(m.group(1))
            break
        grs = rb.gruntly_runs(work)
        child_answer = ""
        for f in (work / ".gruntly" / "runs").glob("*/answer.txt"):
            child_answer = f.read_text(encoding="utf8", errors="replace")[:3000]
        final = rb.save_artifacts(work, runs_dir, stem)
        gsum = rb.gruntly_summary(grs)
        gwall = sum(g.get("wall_s") or 0 for g in gsum)
        (runs_dir / f"{stem}.answer.txt").write_text(answer, encoding="utf8")
        return {"task": name, "bucket": spec["workload"], "workload": spec["workload"], "arm": arm, "rep": rep, "passed": bool(grade["passed"]),
                "score": round(grade["score"], 4), "grade": grade["detail"], "answer": answer[:3000], "child_answer": child_answer,
                "parent_confidence": conf, "parent_model": model, "child_harness": a.child_harness if arm == "forced" else None,
                "child_model": a.child_model if arm == "forced" else None, "needs_web": spec.get("needs_web"),
                "gruntly": gsum, "gruntly_wall_s": gwall, "parent_wall_s": max(wall - gwall, 0), "wall_s": wall, "error": err, **info,
                "gruntly_status": [g["status"] for g in gsum], "gruntly_applied": [g.get("applied") for g in gsum],
                "gruntly_attempts": [g.get("attempts") for g in gsum], "final_patch": final,
                "child_tokens": sum(((g.get("child") or {}).get("tokens") or 0) for g in gsum),
                "child_cost_usd": round(sum(((g.get("child") or {}).get("cost_usd") or 0) for g in gsum), 5), "reviewer_cost_usd": 0.0}


def summary(rows: list[dict]) -> str:
    L = ["# Agent tasks pilot", "", "| task | workload | arm | score | pass | total $ | parent $ | child $ | parent turns | wall s | parent said |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["workload"], r["task"], r["arm"])):
        L.append(f"| {r['task']} | {r['workload']} | {r['arm']} | {r['score']:.2f} | {'yes' if r['passed'] else 'NO'} | {rb.total(r):.3f} | {r['cost_usd']:.3f} | "
                 f"{r.get('child_cost_usd') or 0:.4f} | {r.get('turns')} | {r['wall_s']} | {('%d%%' % r['parent_confidence']) if r.get('parent_confidence') is not None else '-'} |")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--parent-model", default="sonnet")
    ap.add_argument("--child-harness", default="claude")
    ap.add_argument("--child-model", default="haiku")
    ap.add_argument("--child-budget-s", type=int, default=900)
    ap.add_argument("--child-idle-s", type=int, default=300)
    ap.add_argument("--runs-dir", default="runs-agent")
    ap.add_argument("--budget-usd", type=float, default=0.8, help="per-run cap for the parent")
    ap.add_argument("--max-total-usd", type=float, default=0, help="stop before a run whose expected cost (the dearest so far, at least $0.20) would pass this total")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--out", default=str(HERE.parent / "docs" / "benchmarks" / "agent-pilot.md"))
    a = ap.parse_args()
    names = [n for n in a.tasks.split(",") if n] or sorted(p.name for p in TASKS.iterdir() if (p / "task.yaml").is_file())
    raw = Path(a.out).with_suffix(".json")
    rows = json.loads(raw.read_text(encoding="utf8")) if raw.exists() and a.resume else []
    rb.write_meta(Path(str(raw)[:-5] + ".meta.json"), a)
    done = {(r["task"], r["arm"], r["rep"]) for r in rows}
    stop = False
    for rep in range(1, a.reps + 1):
        for n in names:
            for arm in a.arms.split(","):
                if (n, arm, rep) in done:
                    continue
                spent = sum(rb.total(r) for r in rows)
                expect = max([rb.total(r) for r in rows] + [0.20])
                if a.max_total_usd and spent + expect > a.max_total_usd:
                    print(f"stopped: ${spent:.2f} spent, the next run (about ${expect:.2f}) would pass --max-total-usd {a.max_total_usd}", flush=True)
                    stop = True
                    break
                print(f"[{n} / {arm} / rep {rep}] ...", flush=True)
                r = run_one(n, arm, rep, a)
                rows.append(r)
                print(f"  score={r['score']:.2f} pass={r['passed']} total=${rb.total(r):.4f} (child ${r.get('child_cost_usd') or 0:.4f}) turns={r['turns']} "
                      f"wall={r['wall_s']}s said={r.get('parent_confidence')} gruntly={r['gruntly_status']}", flush=True)
                raw.write_text(json.dumps(rows, indent=1), encoding="utf8")
                Path(a.out).write_text(summary(rows), encoding="utf8")
            if stop:
                break
        if stop:
            break
    print(f"wrote {a.out}  (total ${sum(rb.total(r) for r in rows):.2f})")


if __name__ == "__main__":
    main()
