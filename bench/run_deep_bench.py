"""Deep-session benchmark: does delegating beat Claude alone when the session is already long?

Every earlier benchmark started a fresh `claude -p` session per task, where a 4-turn task costs about $0.06 and the session's own
floor ($0.045) is most of it. The user's real sessions are not like that: a turn costs $0.013 to $0.076 because the whole context is
read again every turn. This runs the same ten small tasks, in the same order, inside ONE session that was first primed to about
150k tokens of context, for two arms:

  alone      the parent does each task itself
  delegated  the parent hands each task to gruntly in one call and reads the diff (the old `--holdout` option was removed 2026-11-14)

Each task is its own `claude -p --resume SESSION` call, within the 1-hour cache window; after each one the hidden tests (never shown
to the parent or the child) judge the result. Reported per task: cost, turns, context size, pass, the parent's takeover edits. The
priming turn is reported separately and not charged to either arm's tasks.

  python bench/run_deep_bench.py --dry-run                      # builds the repository and prints the plan; no claude call, no cost
  python bench/run_deep_bench.py --arms alone,delegated --harness hermes --provider nvidia --model poolside/laguna-xs-2.1

WARNING, measured 2026-11-12 (docs/benchmarks/benchmark-deep-alone.md): this design does NOT measure a long interactive session.
Each `claude -p --resume` call re-wrote about 300k tokens of the primed context to the cache (modelUsage: 299k and 301k cache-creation
tokens, about $1.2 a call at $4/M), so a 5-turn task cost $1.47 and $1.61 against about $0.46 for the same turns in the user's real
sessions ($0.076 a turn above 300k tokens). The priming also overshot (83 turns, 226k tokens of context for a 150k target). Redesign
before running again: one process that takes several user messages (`--input-format stream-json`), so the cache stays warm the way it
does interactively. The guards below stop an arm early; they do not fix the artifact.
"""
from __future__ import annotations

import argparse
import importlib.util
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PLUGIN = ROOT / "plugin"
SMALL = ["flatten", "lru_cache", "merge_intervals", "paginate", "parse_duration", "retry", "rolling_mean", "roman", "slugify",
         "word_count"]
TOOLS = ["Bash", "Write", "Read", "Edit", "Glob", "Grep", "Skill"]
CHARS_PER_TOKEN = 4


def _bench():
    spec = importlib.util.spec_from_file_location("run_bench", HERE / "run_bench.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf8", errors="replace", **kw)


# ---------------------------------------------------------------------------------------------- the repository
def context_files(tokens: int) -> list[Path]:
    """Real, public text from this repository, enough to fill `tokens` of context when read: the source first, then the docs."""
    pool = sorted((ROOT / "src" / "gruntly").rglob("*.py")) + sorted((ROOT / "docs").glob("*.md")) \
        + sorted((ROOT / "tests").rglob("*.py"))
    out, used = [], 0
    for p in pool:
        n = len(p.read_text(encoding="utf8", errors="replace")) // CHARS_PER_TOKEN
        if used + n > tokens:
            continue
        out.append(p)
        used += n
    return out


def build_repo(work: Path, tasks: list[str], context_tokens: int, harness: str, model: str, provider: str) -> dict:
    """One repository: `context/` (filler to read) and `tasks/<name>/` (each starter in its own folder). Returns the specs."""
    specs = {}
    (work / "context").mkdir(parents=True)
    for p in context_files(context_tokens):
        dest = work / "context" / p.relative_to(ROOT).as_posix().replace("/", "__")
        dest.write_text(p.read_text(encoding="utf8", errors="replace"), encoding="utf8")
    for name in tasks:
        task_dir = HERE / "tasks" / name
        specs[name] = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf8"))
        shutil.copytree(task_dir / "repo", work / "tasks" / name)
    (work / ".gruntly.toml").write_text(
        f'harness = "{harness}"\nmodel = "{model}"\n' + (f'provider = "{provider}"\n' if provider else "")
        + "budget_s = 900\nno_progress_s = 300\nmax_attempts = 2\n", encoding="utf8")
    sh(["git", "init", "-q", "-b", "main"], work)
    sh(["git", "add", "-A"], work)
    sh(["git", "-c", "user.name=b", "-c", "user.email=b@b", "commit", "-qm", "start"], work)
    return specs


def task_prompt(arm: str, name: str, spec: dict) -> str:
    folder = f"tasks/{name}"
    paths = ", ".join(f"{folder}/{p}" for p in spec["allowed_paths"])
    check = f"python -m pytest -q {folder}"
    brief = " ".join(spec["brief"].split())
    base = (f"New task, in the folder {folder}/ (every file below is inside it).\n{brief}\n\n"
            f"The check is `{check}`, run from the repository root; edit only {paths}.")
    if arm == "alone":
        return base + "\nDo the work yourself and run the check to confirm. Reply in two lines."
    return (base + "\nDelegate this to the child agent through gruntly, as your gruntly skill says: one call, `gruntly agent-run` with "
            "the request in plain words, naming the file and function. Read the diff for behaviour the check does not test (empty and "
            "boundary inputs, error types, not mutating arguments) and send the child corrections in words. Follow the skill's result rules. Reply in two lines.")


PRIME = ("Read every file in the folder context/ with the Read tool (several per turn is fine), one by one, without summarising "
         "them. When you have read them all, reply with the single word: ready.")


# ---------------------------------------------------------------------------------------------- one call
def call(work: Path, prompt: str, session: str | None, arm: str, a, bench) -> dict:
    cmd = [shutil.which("claude") or "claude", "-p", "--allowedTools", *TOOLS, "--output-format", "stream-json", "--verbose",
           "--max-turns", "40", "--max-budget-usd", str(a.budget_usd), "--model", a.parent_model]
    if session:
        cmd += ["--resume", session]
    if arm != "alone":
        cmd += ["--plugin-dir", str(PLUGIN)]
    env = {**os.environ, "BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "600000"}
    t0 = time.time()
    try:
        p = sh(cmd, work, input=prompt, env=env, timeout=2400)       # stdin: the Windows .cmd shim mangles multi-line arguments
        raw, err = p.stdout, None if p.stdout.strip() else (p.stderr or "empty output")[-300:]
    except subprocess.TimeoutExpired:
        raw, err = "", "timeout"
    info = bench.analyse(raw)
    sid = None
    for line in raw.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = e.get("session_id") or sid
    return {"raw": raw, "wall_s": round(time.time() - t0), "error": err, "session": sid, **info}


def judge(work: Path, name: str) -> bool:
    hidden = HERE / "tasks" / name / "hidden" / "test_hidden.py"
    dest = work / "tasks" / name / "test_hidden.py"
    shutil.copy(hidden, dest)
    try:
        return sh([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"tasks/{name}"], work, timeout=180).returncode == 0
    finally:
        dest.unlink(missing_ok=True)


def gruntly_runs(work: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf8")) for p in sorted((work / ".gruntly" / "runs").glob("*/result.json"))]


# ---------------------------------------------------------------------------------------------- the run
def run_arm(arm: str, tasks: list[str], a, bench) -> dict:
    with tempfile.TemporaryDirectory(prefix="deep-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp) / "repo"
        specs = build_repo(work, tasks, a.context_tokens, a.harness, a.model, a.provider)
        out_dir = HERE / a.runs_dir
        out_dir.mkdir(exist_ok=True)
        print(f"[{arm}] priming ({a.context_tokens:,} tokens of context)...", flush=True)
        prime = call(work, PRIME, None, arm, a, bench)
        (out_dir / f"deep.{arm}.prime.jsonl").write_text(prime["raw"], encoding="utf8")
        print(f"  primed: ${prime['cost_usd']} turns={prime['turns']} context={prime['peak_ctx']:,} {prime['error'] or ''}", flush=True)
        rows, session, spent = [], prime["session"], prime["cost_usd"]
        if prime["peak_ctx"] > 1.3 * a.context_tokens + 40_000:      # 40k: Claude Code's own prompt and tools
            print(f"  stopped: the priming left {prime['peak_ctx']:,} tokens of context for a {a.context_tokens:,} target", flush=True)
            return {"arm": arm, "prime": {k: prime[k] for k in ("cost_usd", "turns", "peak_ctx", "error")}, "tasks": rows}
        last = 0.0
        for i, name in enumerate(tasks, 1):
            if spent + max(last, 0.05) > a.max_total_usd:      # the next call is expected to cost about what the last one did
                print(f"  stopped: ${spent:.2f} spent, the next call would pass --max-total-usd ({a.max_total_usd})", flush=True)
                break
            r = call(work, task_prompt(arm, name, specs[name]), session, arm, a, bench)
            session = r["session"] or session
            spent += r["cost_usd"]
            last = r["cost_usd"]
            (out_dir / f"deep.{arm}.{i:02d}.{name}.jsonl").write_text(r.pop("raw"), encoding="utf8")
            grs = gruntly_runs(work)
            r.update(task=name, n=i, arm=arm, passed=judge(work, name), gruntly_status=[g["status"] for g in grs][-1:],
                     reviewer_cost_usd=0.0)
            rows.append(r)
            print(f"  {i:2d} {name:16s} pass={r['passed']} ${r['cost_usd']} turns={r['turns']} ctx={r['peak_ctx']:,} "
                  f"takeover={r['takeover_edits']} wall={r['wall_s']}s {r['error'] or ''}", flush=True)
        return {"arm": arm, "prime": {k: prime[k] for k in ("cost_usd", "turns", "peak_ctx", "error")}, "tasks": rows}


def report(results: list[dict], meta: dict) -> str:
    L = ["# Deep-session benchmark", "",
         f"Parent: Claude Code `{meta['parent_model']}`; child: `{meta['harness']}` / `{meta['model']}` ({meta['provider'] or 'local'}). "
         f"Run {time.strftime('%Y-%m-%d')}. One session per arm, primed to about {meta['context_tokens']:,} tokens, then the same "
         "tasks in the same order with `--resume`. Pass = hidden tests. The priming turn is listed apart and not charged to the tasks.", "",
         "| arm | tasks | pass | cost per task $ | cost of a pass $ | turns per task | takeover edits per task | context at the end | priming $ |",
         "|---|---|---|---|---|---|---|---|---|"]
    for res in results:
        ts = res["tasks"]
        if not ts:
            continue
        rate = sum(t["passed"] for t in ts) / len(ts)
        mean_cost = statistics.fmean(t["cost_usd"] for t in ts)
        L.append(f"| {res['arm']} | {len(ts)} | {rate:.0%} | {mean_cost:.3f} | {mean_cost / rate:.3f} | " if rate else
                 f"| {res['arm']} | {len(ts)} | 0% | {mean_cost:.3f} | inf | ")
        L[-1] += (f"{statistics.fmean(t['turns'] or 0 for t in ts):.1f} | {statistics.fmean(t.get('takeover_edits', 0) for t in ts):.1f} | "
                  f"{ts[-1]['peak_ctx']:,} | {res['prime']['cost_usd']} |")
    L += ["", "## Per task", "", "| # | task | arm | pass | cost $ | turns | context | takeover edits | gruntly | wall s |", "|---|---|---|---|---|---|---|---|---|---|"]
    for res in results:
        for t in res["tasks"]:
            L.append(f"| {t['n']} | {t['task']} | {t['arm']} | {'yes' if t['passed'] else 'NO'} | {t['cost_usd']} | {t['turns']} | "
                     f"{t['peak_ctx']:,} | {t.get('takeover_edits', 0)} | {', '.join(t['gruntly_status']) or '-'} | {t['wall_s']} |")
    L += ["", "Cost is Claude Code's `total_cost_usd` for that call only (the reviewers, if any, are not used in this benchmark). The "
          "child is local or the person's own hosted key and is never counted as money. Ten tasks per arm is a measurement of cost in "
          "a long session, not a quality claim: the order, the cache window and one repetition are fixed (see the protocol in "
          "`docs/investigation-2026-11-11.md` section 9)."]
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arms", default="alone,delegated")
    ap.add_argument("--tasks", default=",".join(SMALL))
    ap.add_argument("--context-tokens", type=int, default=150_000)
    ap.add_argument("--harness", default="hermes")
    ap.add_argument("--model", default="poolside/laguna-xs-2.1")
    ap.add_argument("--provider", default="nvidia")
    ap.add_argument("--parent-model", default="sonnet")
    ap.add_argument("--budget-usd", type=float, default=1.0, help="per-call cap for the parent")
    ap.add_argument("--max-total-usd", type=float, default=3.0, help="stop an arm when its session has cost this much")
    ap.add_argument("--runs-dir", default="runs-deep")
    ap.add_argument("--out", default=str(ROOT / "docs" / "benchmarks" / "benchmark-deep.md"))
    ap.add_argument("--dry-run", action="store_true", help="build the repository, print the plan and the sizes; call nothing")
    a = ap.parse_args()
    tasks = [t for t in a.tasks.split(",") if t]
    bench = _bench()
    if a.dry_run:
        with tempfile.TemporaryDirectory(prefix="deep-dry-", ignore_cleanup_errors=True) as tmp:
            work = Path(tmp) / "repo"
            specs = build_repo(work, tasks, a.context_tokens, a.harness, a.model, a.provider)
            files = sorted((work / "context").iterdir())
            chars = sum(len(p.read_text(encoding="utf8", errors="replace")) for p in files)
            print(f"repository: {len(files)} context files, about {chars // CHARS_PER_TOKEN:,} tokens; {len(tasks)} tasks")
            print(f"\n--- priming prompt ---\n{PRIME}\n")
            for arm in a.arms.split(","):
                print(f"--- {arm}: task 1 ({tasks[0]}) ---\n{task_prompt(arm, tasks[0], specs[tasks[0]])}\n")
        return
    results = []
    for arm in a.arms.split(","):
        results.append(run_arm(arm, tasks, a, bench))
        raw = Path(a.out).with_suffix(".json")
        raw.write_text(json.dumps(results, indent=1), encoding="utf8")
        Path(a.out).write_text(report(results, vars(a)), encoding="utf8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
