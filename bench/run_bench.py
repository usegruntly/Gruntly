"""Runs every bench task two ways with Claude Code as the parent, then judges with the hidden tests.

  alone    claude does the task itself
  gruntly  claude delegates through the gruntly plugin skill, verifies, applies

Honest accounting: the parent's tokens and cost come from `claude -p --output-format json` for the WHOLE
session, so any takeover work after an escalation is counted. The local model's tokens are reported
separately because they cost no paid tokens. Usage:

  python bench/run_bench.py --harness opencode --model qwen/qwen3.5-9b [--tasks slugify,retry] [--modes alone,gruntly]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
PLUGIN = HERE.parent / "plugin"
TOOLS = ["Bash", "Write", "Read", "Edit", "Glob", "Grep", "Skill"]


def sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf8", errors="replace", **kw)


def prepare(task_dir: Path, work: Path, harness: str, model: str) -> dict:
    spec = __import__("yaml").safe_load((task_dir / "task.yaml").read_text(encoding="utf8"))
    shutil.copytree(task_dir / "repo", work)
    (work / ".gruntly.toml").write_text(
        f'harness = "{harness}"\nmodel = "{model}"\nbudget_s = 600\nno_progress_s = 240\nmax_attempts = 2\n', encoding="utf8")
    sh(["git", "init", "-q", "-b", "main"], work)
    sh(["git", "add", "-A"], work)
    sh(["git", "-c", "user.name=b", "-c", "user.email=b@b", "commit", "-qm", "start"], work)
    return spec


def prompt_for(mode: str, spec: dict) -> str:
    cmd = spec["acceptance"][0]["cmd"]
    paths = ", ".join(spec["allowed_paths"])
    if mode == "alone":
        return f"{spec['brief']}\n\nEdit only {paths}. Do the work yourself and run `{cmd}` to confirm. Reply in two lines."
    return (f"{spec['brief']}\n\nDelegate this to the local model with your gruntly skill (allowed_paths: {paths}; "
            f"acceptance: `{cmd}`). Verify the way the skill says, apply it, and reply in two lines. "
            f"If gruntly escalates, follow the skill's playbook. Do not write the solution yourself unless it says to take over.")


def judge(task_dir: Path, work: Path) -> bool:
    shutil.copy(task_dir / "hidden" / "test_hidden.py", work / "test_hidden.py")
    r = sh([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], work, timeout=120)
    (work / "test_hidden.py").unlink()
    return r.returncode == 0


def tokens(usage: dict) -> dict:
    u = usage or {}
    return {"input": u.get("input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
            "cache_read": u.get("cache_read_input_tokens", 0), "output": u.get("output_tokens", 0)}


def gruntly_runs(work: Path) -> list[dict]:
    out = []
    for p in sorted((work / ".gruntly" / "runs").glob("*/result.json")) if (work / ".gruntly" / "runs").exists() else []:
        out.append(json.loads(p.read_text(encoding="utf8")))
    return out


def run_one(task_dir: Path, mode: str, harness: str, model: str, parent_model: str | None, budget: float) -> dict:
    with tempfile.TemporaryDirectory(prefix="bench-") as tmp:
        work = Path(tmp) / "repo"
        spec = prepare(task_dir, work, harness, model)
        cmd = ["claude", "-p", prompt_for(mode, spec), "--allowedTools", *TOOLS, "--output-format", "json",
               "--max-turns", "30", "--max-budget-usd", str(budget), "--no-session-persistence"]
        if parent_model:
            cmd += ["--model", parent_model]
        if mode == "gruntly":
            cmd += ["--plugin-dir", str(PLUGIN)]
        t0 = time.time()
        try:
            p = sh(cmd, work, timeout=1500)
            data = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {"error": (p.stderr or p.stdout)[-300:]}
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            data = {"error": f"{type(e).__name__}"}
        wall = round(time.time() - t0)
        grs = gruntly_runs(work)
        child_tokens = sum(((r.get("child_usage") or {}).get("total_tokens") or 0) for r in grs)
        return {"task": task_dir.name, "mode": mode, "passed": judge(task_dir, work),
                "cost_usd": round(data.get("total_cost_usd") or 0, 4), "turns": data.get("num_turns"),
                "wall_s": wall, "tokens": tokens(data.get("usage")), "error": data.get("error"),
                "gruntly_status": [r["status"] for r in grs], "gruntly_attempts": [r["attempts"] for r in grs],
                "gruntly_result_chars": [len(json.dumps(r)) for r in grs], "child_tokens": child_tokens}


def report(rows: list[dict], meta: dict) -> str:
    def agg(mode):
        rs = [r for r in rows if r["mode"] == mode]
        n = len(rs) or 1
        return {"n": len(rs), "pass": sum(r["passed"] for r in rs), "cost": sum(r["cost_usd"] for r in rs),
                "out": sum(r["tokens"]["output"] for r in rs),
                "ctx": sum(r["tokens"]["input"] + r["tokens"]["cache_write"] + r["tokens"]["cache_read"] for r in rs),
                "wall": sum(r["wall_s"] for r in rs) / n, "child": sum(r["child_tokens"] for r in rs)}
    lines = [f"# gruntly benchmark", "",
             f"Local child: `{meta['harness']}` / `{meta['model']}`. Parent: Claude Code ({meta.get('parent_model') or 'default model'}). "
             f"Run on {time.strftime('%Y-%m-%d')}. Pass = hidden tests (never shown to parent or child) pass after the run.", "",
             "| task | mode | pass | cost $ | parent out tok | parent ctx tok | turns | wall s | gruntly status (attempts) | child tok |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["task"], r["mode"])):
        t = r["tokens"]
        gs = ", ".join(f"{s} ({a})" for s, a in zip(r["gruntly_status"], r["gruntly_attempts"])) or "-"
        lines.append(f"| {r['task']} | {r['mode']} | {'yes' if r['passed'] else 'NO'} | {r['cost_usd']:.3f} | {t['output']} | "
                     f"{t['input'] + t['cache_write'] + t['cache_read']} | {r['turns']} | {r['wall_s']} | {gs} | {r['child_tokens'] or '-'} |")
    lines += ["", "## Totals", "", "| mode | tasks | passed | total cost $ | parent output tok | parent context tok | mean wall s | local child tok |",
              "|---|---|---|---|---|---|---|---|"]
    for m in ("alone", "gruntly"):
        a = agg(m)
        if a["n"]:
            lines.append(f"| {m} | {a['n']} | {a['pass']} | {a['cost']:.3f} | {a['out']} | {a['ctx']} | {a['wall']:.0f} | {a['child'] or '-'} |")
    errs = [r for r in rows if r.get("error")]
    if errs:
        lines += ["", "Errors: " + "; ".join(f"{r['task']}/{r['mode']}: {r['error']}" for r in errs)]
    lines += ["", "Accounting notes: parent tokens and cost cover the whole Claude session, including any takeover after an escalation. "
              "Context tokens include cache reads, which are billed at a lower rate; cost is Claude Code's own `total_cost_usd`. "
              "Local child tokens are free of paid cost but cost wall time. Tasks are small synthetic functions, so treat the numbers as "
              "a floor on task difficulty, not a verdict; add tasks from your own repos under `bench/tasks/`."]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", default="opencode")
    ap.add_argument("--model", default="qwen/qwen3.5-9b")
    ap.add_argument("--parent-model", default=None)
    ap.add_argument("--tasks", default="")
    ap.add_argument("--modes", default="alone,gruntly")
    ap.add_argument("--budget-usd", type=float, default=1.0, help="per-run cap for the parent")
    ap.add_argument("--out", default=str(HERE.parent / "docs" / "benchmark.md"))
    a = ap.parse_args()
    names = [n for n in a.tasks.split(",") if n] or sorted(p.name for p in (HERE / "tasks").iterdir() if p.is_dir())
    rows = []
    raw = Path(a.out).with_suffix(".json")
    for n in names:
        for m in a.modes.split(","):
            print(f"[{n} / {m}] ...", flush=True)
            r = run_one(HERE / "tasks" / n, m, a.harness, a.model, a.parent_model, a.budget_usd)
            rows.append(r)
            print(f"  pass={r['passed']} cost=${r['cost_usd']} wall={r['wall_s']}s gruntly={r['gruntly_status']}", flush=True)
            raw.write_text(json.dumps(rows, indent=1), encoding="utf8")
    Path(a.out).write_text(report(rows, vars(a)), encoding="utf8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
