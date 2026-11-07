"""Runs bench tasks with Claude Code as the parent, in three arms, then judges with hidden tests.

  alone    claude does the task itself
  forced   claude is told to delegate through gruntly's one-call flow (measures the flow's overhead)
  policy   claude is told gruntly exists and may use it if it judges it worthwhile (measures the triage rule)

Honest accounting: tokens and cost come from the WHOLE Claude session (`claude -p --output-format stream-json`),
so takeover work after an escalation is counted. Transcripts are kept under bench/runs/ so turns can be attributed
to tool calls. Local child tokens are reported separately: they cost no paid tokens but cost wall time.

  python bench/run_bench.py --harness opencode --model qwen/qwen3.5-9b --arms alone,forced,policy --reps 2 \
      --tasks slugify,retry,bugs_batch --resume
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

HERE = Path(__file__).parent
PLUGIN = HERE.parent / "plugin"
TOOLS = ["Bash", "Write", "Read", "Edit", "Glob", "Grep", "Skill"]
LARGE = {"bugs_batch", "rename_domain", "cli_json"}


def sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf8", errors="replace", **kw)


def bucket(task: str) -> str:
    return "L" if task in LARGE else "S"


def prepare(task_dir: Path, work: Path, harness: str, model: str) -> dict:
    spec = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf8"))
    shutil.copytree(task_dir / "repo", work)
    (work / ".gruntly.toml").write_text(
        f'harness = "{harness}"\nmodel = "{model}"\nbudget_s = 900\nno_progress_s = 300\nmax_attempts = 2\n', encoding="utf8")
    sh(["git", "init", "-q", "-b", "main"], work)
    sh(["git", "add", "-A"], work)
    sh(["git", "-c", "user.name=b", "-c", "user.email=b@b", "commit", "-qm", "start"], work)
    return spec


def prompt_for(arm: str, spec: dict) -> str:
    cmd = spec["acceptance"][0]["cmd"]
    paths = ", ".join(spec["allowed_paths"])
    extra = " You may edit the existing tests." if spec.get("tests_writable") else ""
    base = spec["brief"] + f"\n\nThe check is `{cmd}`; edit only {paths}.{extra}"
    if arm == "alone":
        return base + "\nDo the work yourself and run the check to confirm. Reply in two lines."
    if arm == "forced":
        return (base + "\nDelegate this to the local model with your gruntly skill, using its one-call flow "
                       "(`gruntly run --apply-on-pass`). Follow the skill's result rules. If gruntly escalates, do it yourself. Reply in two lines.")
    return (base + "\nThe gruntly plugin is available. Use it only if your gruntly skill says delegating is worthwhile for a "
                   "task like this; otherwise just do the work yourself. Run the check to confirm. Reply in two lines.")


def judge(task_dir: Path, work: Path) -> bool:
    shutil.copy(task_dir / "hidden" / "test_hidden.py", work / "test_hidden.py")
    r = sh([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], work, timeout=180)
    (work / "test_hidden.py").unlink()
    return r.returncode == 0


def analyse(raw: str) -> dict:
    """Turns, cost, context and tool-output size from a stream-json transcript."""
    tool_bytes = peak = 0
    tools: dict[str, int] = {}
    result: dict = {}
    for line in raw.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = e.get("type")
        if t == "assistant":
            msg = e.get("message", {})
            u = msg.get("usage") or {}
            peak = max(peak, (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                       + (u.get("cache_creation_input_tokens") or 0))
            for b in msg.get("content", []):
                if b.get("type") == "tool_use":
                    tools[b.get("name", "?")] = tools.get(b.get("name", "?"), 0) + 1
        elif t == "user":
            for b in (e.get("message", {}).get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    tool_bytes += len(c if isinstance(c, str) else json.dumps(c))
        elif t == "result":
            result = e
    u = result.get("usage") or {}
    return {"cost_usd": round(result.get("total_cost_usd") or 0, 4), "turns": result.get("num_turns"),
            "reply": (result.get("result") or "")[:500], "tools": tools, "tool_output_bytes": tool_bytes, "peak_ctx": peak,
            "tokens": {"input": u.get("input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
                       "cache_read": u.get("cache_read_input_tokens", 0), "output": u.get("output_tokens", 0)}}


def gruntly_runs(work: Path) -> list[dict]:
    d = work / ".gruntly" / "runs"
    return [json.loads(p.read_text(encoding="utf8")) for p in sorted(d.glob("*/result.json"))] if d.exists() else []


def run_one(task_dir: Path, arm: str, rep: int, a) -> dict:
    with tempfile.TemporaryDirectory(prefix="bench-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp) / "repo"
        spec = prepare(task_dir, work, a.harness, a.model)
        cmd = [shutil.which("claude") or "claude", "-p", "--allowedTools", *TOOLS, "--output-format", "stream-json", "--verbose",
               "--max-turns", "40", "--max-budget-usd", str(a.budget_usd)]
        if a.parent_model:
            cmd += ["--model", a.parent_model]
        if arm != "alone":
            cmd += ["--plugin-dir", str(PLUGIN)]
        t0 = time.time()
        err = None
        try:
            p = sh(cmd, work, timeout=2400, input=prompt_for(arm, spec))  # stdin: the Windows .cmd shim mangles multi-line args
            raw = p.stdout
            if not raw.strip():
                err = (p.stderr or "empty output")[-300:]
        except subprocess.TimeoutExpired:
            raw, err = "", "timeout"
        wall = round(time.time() - t0)
        runs_dir = HERE / "runs"
        runs_dir.mkdir(exist_ok=True)
        (runs_dir / f"{task_dir.name}.{arm}.{rep}.jsonl").write_text(raw, encoding="utf8")
        info = analyse(raw)
        grs = gruntly_runs(work)
        return {"task": task_dir.name, "bucket": bucket(task_dir.name), "arm": arm, "rep": rep, "passed": judge(task_dir, work),
                "wall_s": wall, "error": err, **info, "gruntly_status": [r["status"] for r in grs],
                "gruntly_applied": [r.get("applied") for r in grs], "gruntly_attempts": [r["attempts"] for r in grs],
                "gruntly_result_chars": [len(json.dumps(r)) for r in grs],
                "child_tokens": sum(r.get("child_tokens") or 0 for r in grs)}


def mean(xs):
    return statistics.fmean(xs) if xs else 0.0


def report(rows: list[dict], meta: dict) -> str:
    arms = [x for x in ("alone", "forced", "policy") if any(r["arm"] == x for r in rows)]
    L = ["# gruntly benchmark (v2)", "",
         f"Local child: `{meta['harness']}` / `{meta['model']}` at 32k context. Parent: Claude Code ({meta.get('parent_model') or 'default model'}). "
         f"Run {time.strftime('%Y-%m-%d')}. Pass = hidden tests (never shown to the parent or the child) pass afterwards. "
         "S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature). "
         "Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).", "",
         "## Totals by bucket (means over tasks and repetitions)", "",
         "| bucket | arm | runs | pass rate | cost $/run | vs alone | turns | wall s | parent output tok | tool-output KB in context | delegated | child tok |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for b in ("S", "L"):
        base = [r["cost_usd"] for r in rows if r["bucket"] == b and r["arm"] == "alone"]
        for arm in arms:
            rs = [r for r in rows if r["bucket"] == b and r["arm"] == arm]
            if not rs:
                continue
            rel = f"{mean([r['cost_usd'] for r in rs]) / mean(base) - 1:+.0%}" if base and arm != "alone" else "-"
            deleg = sum(1 for r in rs if r["gruntly_status"])
            L.append(f"| {b} | {arm} | {len(rs)} | {mean([r['passed'] for r in rs]):.0%} | {mean([r['cost_usd'] for r in rs]):.3f} | {rel} | "
                     f"{mean([r['turns'] or 0 for r in rs]):.1f} | {mean([r['wall_s'] for r in rs]):.0f} | "
                     f"{mean([r['tokens']['output'] for r in rs]):.0f} | {mean([r['tool_output_bytes'] for r in rs]) / 1024:.1f} | "
                     f"{deleg}/{len(rs)} | {sum(r['child_tokens'] for r in rs) or '-'} |")
    L += ["", "## Per task (mean over repetitions)", "",
          "| task | arm | pass | cost $ | turns | wall s | gruntly (status, attempts) | false pass |", "|---|---|---|---|---|---|---|---|"]
    for task in sorted({r["task"] for r in rows}):
        for arm in arms:
            rs = [r for r in rows if r["task"] == task and r["arm"] == arm]
            if not rs:
                continue
            g = "; ".join(f"{s}{'+applied' if ap else ''} ({n})" for r in rs for s, ap, n in
                          zip(r["gruntly_status"], r["gruntly_applied"], r["gruntly_attempts"])) or "-"
            fp = sum(1 for r in rs if not r["passed"] and "passed" in r["gruntly_status"])
            L.append(f"| {task} | {arm} | {sum(r['passed'] for r in rs)}/{len(rs)} | {mean([r['cost_usd'] for r in rs]):.3f} | "
                     f"{mean([r['turns'] or 0 for r in rs]):.1f} | {mean([r['wall_s'] for r in rs]):.0f} | {g} | {fp or '-'} |")
    errs = [r for r in rows if r.get("error")]
    if errs:
        L += ["", "Errors: " + "; ".join(f"{r['task']}/{r['arm']}#{r['rep']}: {r['error']}" for r in errs)]
    L += ["", "Accounting: parent cost is Claude Code's own `total_cost_usd` for the whole session (cache reads included), so any "
          "takeover after an escalation is counted. Local child tokens are free of paid cost but cost wall time. "
          "False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", default="opencode")
    ap.add_argument("--model", default="qwen/qwen3.5-9b")
    ap.add_argument("--parent-model", default=None)
    ap.add_argument("--tasks", default="")
    ap.add_argument("--arms", default="alone,forced,policy")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--budget-usd", type=float, default=1.5, help="per-run cap for the parent")
    ap.add_argument("--resume", action="store_true", help="continue from the saved .json next to --out")
    ap.add_argument("--out", default=str(HERE.parent / "docs" / "benchmark-v2.md"))
    a = ap.parse_args()
    names = [n for n in a.tasks.split(",") if n] or sorted(p.name for p in (HERE / "tasks").iterdir() if p.is_dir())
    raw = Path(a.out).with_suffix(".json")
    rows = json.loads(raw.read_text(encoding="utf8")) if raw.exists() and a.resume else []
    done = {(r["task"], r["arm"], r["rep"]) for r in rows}
    for rep in range(1, a.reps + 1):
        for n in names:
            for arm in a.arms.split(","):
                if (n, arm, rep) in done:
                    continue
                print(f"[{n} / {arm} / rep {rep}] ...", flush=True)
                r = run_one(HERE / "tasks" / n, arm, rep, a)
                rows.append(r)
                print(f"  pass={r['passed']} ${r['cost_usd']} turns={r['turns']} wall={r['wall_s']}s gruntly={r['gruntly_status']}", flush=True)
                raw.write_text(json.dumps(rows, indent=1), encoding="utf8")
                Path(a.out).write_text(report(rows, vars(a)), encoding="utf8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
