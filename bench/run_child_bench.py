"""Child-only benchmark: which profile should the local model get? Costs no paid tokens (no Claude involved).

Drives `gruntly run --apply-on-pass` directly against the local model for every (task, brief, arm, repetition) and
judges the result with the task's hidden tests, which neither gruntly nor the child ever sees.

Arms are `<profile>[-self]`: `default` (the harness as shipped), `typist`, `worker`; the `-self` suffix lets the child
run the acceptance command itself (instead of evaluate & fix, where gruntly runs the tests and feeds the errors back).

  python bench/run_child_bench.py --harness opencode --model qwen/qwen3.5-9b \
      --arms default,typist,typist-self,worker --briefs precise,vague --reps 2
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

HERE = Path(__file__).parent
VAGUE = yaml.safe_load((HERE / "vague_briefs.yaml").read_text(encoding="utf8"))


def sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf8", errors="replace", **kw)


def arm_settings(arm: str) -> dict:
    profile, _, suffix = arm.partition("-")
    if profile not in ("default", "typist", "worker", "auto") or suffix not in ("", "self"):
        raise SystemExit(f"bad arm {arm!r}: use default, typist, worker, auto, optionally with -self")
    return {"profile": profile, "self_check": suffix == "self"}


def build_spec(task_dir: Path, brief: str, arm: str, a) -> dict:
    spec = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf8"))
    if brief == "vague":
        spec["brief"] = " ".join(VAGUE[task_dir.name].split())
    spec.update(arm_settings(arm))
    spec.update({"max_attempts": a.max_attempts, "budget_s": a.budget_s, "no_progress_s": 300, "apply_on_pass": True,
                 "harness": a.harness, "model": a.model})
    return spec


def judge(task_dir: Path, work: Path) -> bool:
    shutil.copy(task_dir / "hidden" / "test_hidden.py", work / "test_hidden.py")
    r = sh([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], work, timeout=180)
    (work / "test_hidden.py").unlink()
    return r.returncode == 0


def run_one(task_dir: Path, brief: str, arm: str, rep: int, a) -> dict:
    with tempfile.TemporaryDirectory(prefix="cbench-", ignore_cleanup_errors=True) as tmp:
        work, state = Path(tmp) / "repo", Path(tmp) / "state"
        shutil.copytree(task_dir / "repo", work)
        sh(["git", "init", "-q", "-b", "main"], work)
        sh(["git", "add", "-A"], work)
        sh(["git", "-c", "user.name=b", "-c", "user.email=b@b", "commit", "-qm", "start"], work)
        spec = build_spec(task_dir, brief, arm, a)
        env = {**os.environ, "GRUNTLY_STATE_DIR": str(state), "GRUNTLY_CONFIG_DIR": str(Path(tmp) / "cfg")}
        t0 = time.time()
        p = sh([sys.executable, "-m", "gruntly", "run", "--spec", "-", "--max-block", "0"], work, input=yaml.safe_dump(spec), env=env, timeout=a.budget_s + 600)
        wall = round(time.time() - t0)
        try:
            res = json.loads(p.stdout)
        except json.JSONDecodeError:
            res = {"status": "error", "error": (p.stderr or p.stdout)[-300:], "attempts": 0}
        idx = state / "runs.jsonl"
        usage = {}
        if idx.exists():
            lines = idx.read_text(encoding="utf8").strip().splitlines()
            usage = (json.loads(lines[-1]).get("child_usage") or {}) if lines else {}
        return {"task": task_dir.name, "brief": brief, "arm": arm, "rep": rep, "status": res.get("status"),
                "attempts": res.get("attempts", 0), "first_try": res.get("status") == "passed" and res.get("attempts") == 1,
                "hidden_pass": judge(task_dir, work), "wall_s": wall, "child_tokens": usage.get("total_tokens") or 0,
                "requests": usage.get("requests") or 0, "input_per_request": usage.get("input_per_request"),
                "warnings": res.get("warnings"), "error": res.get("error"),
                "reason": (res.get("failure_bundle") or {}).get("reason")}


def pct(xs):
    return f"{100 * statistics.fmean(xs):.0f}%" if xs else "-"


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else 0


def report(rows: list[dict], meta: dict) -> str:
    arms = sorted({r["arm"] for r in rows}, key=lambda x: (x.split("-")[0] != "default", x))
    L = ["# Child benchmark: which profile should the local model get?", "",
         f"Local child `{meta['harness']}` / `{meta['model']}`, no Claude involved ({time.strftime('%Y-%m-%d')}). Each run is "
         "`gruntly run --apply-on-pass` judged by hidden tests. Arms: `default` = the harness as shipped; `typist` / `worker` = slim "
         "profiles; suffix `-self` = the child may run the acceptance command itself (otherwise gruntly evaluates and feeds errors back). "
         "`precise` briefs are the normal ones; `vague` briefs leave out names, edge cases and the method.", ""]
    for brief in ("precise", "vague"):
        rs = [r for r in rows if r["brief"] == brief]
        if not rs:
            continue
        L += [f"## {brief} briefs", "", "| arm | runs | first-try pass | hidden-test pass | false pass | escalated | input tok/request | child tok/run | requests/run | wall s |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for arm in arms:
            x = [r for r in rs if r["arm"] == arm]
            if not x:
                continue
            fp = sum(1 for r in x if r["status"] == "passed" and not r["hidden_pass"])
            esc = sum(1 for r in x if r["status"] in ("escalate", "timeout", "error"))
            L.append(f"| {arm} | {len(x)} | {pct([r['first_try'] for r in x])} | {pct([r['hidden_pass'] for r in x])} | {fp} | {esc} | "
                     f"{mean([r['input_per_request'] for r in x]):.0f} | {mean([r['child_tokens'] for r in x]):.0f} | "
                     f"{mean([r['requests'] for r in x]):.1f} | {mean([r['wall_s'] for r in x]):.0f} |")
        L.append("")
    L += ["## Per task (hidden-test passes / runs)", "", "| task | brief | " + " | ".join(arms) + " |", "|---|---|" + "---|" * len(arms)]
    for task in sorted({r["task"] for r in rows}):
        for brief in ("precise", "vague"):
            cells = []
            for arm in arms:
                x = [r for r in rows if r["task"] == task and r["brief"] == brief and r["arm"] == arm]
                cells.append(f"{sum(r['hidden_pass'] for r in x)}/{len(x)}" if x else "-")
            if any(c != "-" for c in cells):
                L.append(f"| {task} | {brief} | " + " | ".join(cells) + " |")
    L += ["", "False pass = gruntly reported `passed` (all its gates green) but the hidden tests failed.",
          "Decision rule (docs/plan): adopt typist where its hidden-test pass rate is within 5 points of `default` and it uses at least "
          "40% fewer child tokens; adopt worker where its vague-brief pass rate beats typist by at least 15 points."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", default="opencode")
    ap.add_argument("--model", default="qwen/qwen3.5-9b")
    ap.add_argument("--arms", default="default,typist,worker")
    ap.add_argument("--briefs", default="precise")
    ap.add_argument("--tasks", default="")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--budget-s", type=int, default=600)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(HERE.parent / "docs" / "child-bench.md"))
    a = ap.parse_args()
    all_tasks = sorted(p.name for p in (HERE / "tasks").iterdir() if p.is_dir())
    names = [n for n in a.tasks.split(",") if n] or all_tasks
    raw = Path(a.out).with_suffix(".json")
    rows = json.loads(raw.read_text(encoding="utf8")) if raw.exists() and a.resume else []
    done = {(r["task"], r["brief"], r["arm"], r["rep"]) for r in rows}
    plan = [(n, b, arm, rep) for rep in range(1, a.reps + 1) for n in names for b in a.briefs.split(",") for arm in a.arms.split(",")
            if (b != "vague" or n in VAGUE) and (n, b, arm, rep) not in done]
    print(f"{len(plan)} runs planned")
    if a.dry_run:
        for n, b, arm, rep in plan:
            print(" ", n, b, arm, rep, arm_settings(arm))
        return
    for n, b, arm, rep in plan:
        print(f"[{n} / {b} / {arm} / rep {rep}] ...", flush=True)
        r = run_one(HERE / "tasks" / n, b, arm, rep, a)
        rows.append(r)
        print(f"  {r['status']} attempts={r['attempts']} hidden={r['hidden_pass']} tok={r['child_tokens']} "
              f"in/req={r['input_per_request']} wall={r['wall_s']}s", flush=True)
        raw.write_text(json.dumps(rows, indent=1), encoding="utf8")
        Path(a.out).write_text(report(rows, vars(a)), encoding="utf8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
