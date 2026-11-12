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

HERE = Path(__file__).parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))          # real_tasks.py sits beside this file, also when this file is loaded by path
PLUGIN = HERE.parent / "plugin"
TOOLS = ["Bash", "Write", "Read", "Edit", "Glob", "Grep", "Skill"]
LARGE = {"bugs_batch", "rename_domain", "cli_json", "inventory_reorder", "settings_refactor"}
# per-arm `[do]` settings for the slash-command arms: gd = old behaviour, gdA = diff in the request, gdAB = diff + hints
DO_TOML = {"gd": "\n[do]\ndiff = false\nhints = false\n", "gdA": "\n[do]\ndiff = true\nhints = false\n",
           "gdAB": "\n[do]\ndiff = true\nhints = true\n"}
GD_ARMS = tuple(DO_TOML)
LEAN_ALONE_PROMPT = ("You are a coding agent working in this repository. Do the task yourself with your tools, run the check "
                     "to confirm it passes, then reply in one line.")
LEAN_ALONE = "lean_alone"   # the same stripped-down Claude doing the task itself: the matched baseline for `lean`
SUBAGENT = "subagent"   # Claude Code's own answer: the edit done by a Haiku sub-agent inside the session
SUPERVISED = "supervised"   # one call; the child plans and works in steps, a reviewer (outside the session) checks each
PLANNER = "planner"   # Claude plans and supervises; the child finds the code and does the work (`agent-run --explore`)
LEAN = "lean"   # a stripped-down Claude (one Bash tool, one-line system prompt) directing gruntly via `gruntly agent-run`


def sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf8", errors="replace", **kw)


def task_dir_of(name: str) -> Path:
    """Synthetic tasks live in bench/tasks, tasks from real repositories in bench/tasks-real (see real_tasks.py)."""
    return HERE / "tasks" / name if (HERE / "tasks" / name).is_dir() else HERE / "tasks-real" / name


def bucket(task: str) -> str:
    return "R" if (HERE / "tasks-real" / task).is_dir() else "L" if task in LARGE else "S"


def prepare(task_dir: Path, work: Path, harness: str, model: str, extra: str = "", provider: str = "",
            budget_s: int = 900, no_progress_s: int = 300) -> dict:
    spec = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf8"))
    if (task_dir / "repo").is_dir():
        shutil.copytree(task_dir / "repo", work)
    else:                                       # a task from a real repository: the starter is the parent commit
        import real_tasks
        real_tasks.materialize(spec["source"], work)
        for a_ in spec.get("acceptance", []):       # the check must run on the interpreter the benchmark controls
            a_["cmd"] = a_["cmd"].replace("python ", f'"{Path(sys.executable).as_posix()}" ', 1)
    (work / ".gruntly.toml").write_text(
        f'harness = "{harness}"\nmodel = "{model}"\n' + (f'provider = "{provider}"\n' if provider else "")
        + f'budget_s = {budget_s}\nno_progress_s = {no_progress_s}\nmax_attempts = 2\n' + extra, encoding="utf8")
    sh(["git", "init", "-q", "-b", "main"], work)
    sh(["git", "add", "-A"], work)
    sh(["git", "-c", "user.name=b", "-c", "user.email=b@b", "commit", "-qm", "start"], work)
    return spec


def rate_limits_toml(text: str) -> str:
    """`rpm=10,tpm=250000` -> a [rate_limits] table for the work copy's .gruntly.toml ('' for no override)."""
    pairs = [p.strip().split("=", 1) for p in text.split(",") if p.strip()]
    if not pairs:
        return ""
    return "\n[rate_limits]\n" + "".join(f"{k.strip()} = {int(v)}\n" for k, v in pairs)


def prompt_for(arm: str, spec: dict) -> str:
    cmd = spec["acceptance"][0]["cmd"]
    paths = ", ".join(spec["allowed_paths"])
    extra = " You may edit the existing tests." if spec.get("tests_writable") else ""
    base = spec["brief"] + f"\n\nThe check is `{cmd}`; edit only {paths}.{extra}"
    if arm == SUBAGENT:
        return (base + "\nDo not read or edit the files yourself. Delegate the implementation to ONE sub-agent on the haiku model: "
                "call the Agent tool with model set to haiku and a prompt that names the files, every behaviour that must hold "
                "and the check command, and tells it to run the check before it finishes. When its report comes back, run "
                "the check once yourself and reply in two lines.")
    if arm == SUPERVISED:
        return (" ".join(spec["brief"].split()) + f"\n\nThe check is `{cmd}`.\n"
                "Delegate the whole task with one foreground Bash call (timeout 3600000): gruntly agent-run --supervised "
                f"--max-block 3500 --check '{cmd}' 'THE TASK IN PLAIN WORDS, with every requirement above'. If the block says running, call "
                "gruntly wait RUN_ID the same way until it is done. Read only the block. If it passed, reply in two lines; "
                "if it failed, finish the rest yourself.")
    if arm == PLANNER:
        return (" ".join(spec["brief"].split()) + f"\n\nThe check is `{cmd}`.\n"
                "You are the planner and supervisor; a child coding agent does the work. Do not read, search or edit the code "
                "yourself. 1) Write a short numbered plan in plain words: what has to be true, not where the code is (the child "
                "finds that). 2) Delegate each step with one foreground Bash call (timeout 600000): "
                f"gruntly agent-run --explore --check '{cmd}' 'STEP IN PLAIN WORDS'. 3) Track each step from its result block: "
                "passed and the diff does the step = done; a gap = gruntly agent-run --continue RUN_ID 'what to change'; "
                "failed twice = say so and stop. Reply with each step and its outcome in a few lines.")
    if arm == LEAN:
        return " ".join(spec["brief"].split())
    if arm == LEAN_ALONE:
        return base + "\nReply in one line."
    if arm in GD_ARMS:  # the one-request slash command: just the user's words, nothing else
        return "/gruntly:gd " + " ".join(spec["brief"].split())
    if arm == "alone":
        return base + "\nDo the work yourself and run the check to confirm. Reply in two lines."
    if arm == "forced":
        return (base + "\nDelegate this to the child agent through gruntly, as your gruntly skill says (one call: "
                       "`gruntly agent-run` with the request in plain words). Follow the skill's result rules. If gruntly fails, "
                       "do it yourself. Reply in two lines.")
    return (base + "\nThe gruntly plugin is available. Use it only if your gruntly skill says delegating is worthwhile for a "
                   "task like this; otherwise just do the work yourself. Run the check to confirm. Reply in two lines.")


def judge(task_dir: Path, work: Path) -> bool:
    judge.last = ""
    if not (task_dir / "hidden" / "test_hidden.py").is_file():       # real task: the fix commit's own tests
        import real_tasks
        ok = real_tasks.judge_files(task_dir, work)
        p = getattr(real_tasks.judge_files, "last", None)
        judge.last = ((p.stdout or "") + (p.stderr or "")) if p else ""
        return ok
    shutil.copy(task_dir / "hidden" / "test_hidden.py", work / "test_hidden.py")
    r = sh([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], work, timeout=180)
    (work / "test_hidden.py").unlink()
    judge.last = (r.stdout or "") + (r.stderr or "")
    return r.returncode == 0


def judge_detail() -> dict:
    """What the hidden tests said, beyond pass/fail: case counts (a fix that fails 2 of 36 cases is not a fix that fails 30) and the
    names of the cases that failed."""
    out = getattr(judge, "last", "") or ""
    def n(word):
        m = re.findall(rf"(\d+) {word}", out)
        return int(m[-1]) if m else 0
    failed = [l.split(" - ")[0].replace("FAILED ", "").strip()[:160] for l in out.splitlines() if l.startswith("FAILED ")]
    return {"cases_passed": n("passed"), "cases_failed": n("failed"), "cases_error": n("error"), "failed": failed[:12],
            "tail": "\n".join(out.strip().splitlines()[-6:])[:600]}


def save_artifacts(work: Path, runs_dir: Path, stem: str) -> dict:
    """Keep the raw material of a run so any metric can be recomputed later: gruntly's own records (result, child log, per-attempt
    prompts, diffs and gate output) and the final patch, whoever made it. The temporary work copy is deleted afterwards."""
    src = work / ".gruntly" / "runs"
    if src.is_dir():
        shutil.copytree(src, runs_dir / f"{stem}.gruntly", dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.pyc", "__pycache__"))
    sh(["git", "add", "-A"], work)
    d = sh(["git", "diff", "--cached", "HEAD", "--", ".", ":!.gruntly", ":!.gruntly.toml", ":!**/__pycache__/**", ":!**/*.pyc",
            ":!**/.pytest_cache/**"], work).stdout
    (runs_dir / f"{stem}.final.patch").write_text(d, encoding="utf8")
    add = sum(1 for l in d.splitlines() if l.startswith("+") and not l.startswith("+++"))
    dele = sum(1 for l in d.splitlines() if l.startswith("-") and not l.startswith("---"))
    return {"lines_added": add, "lines_removed": dele, "files": len(re.findall(r"^diff --git ", d, re.M))}


def gruntly_summary(grs: list[dict]) -> list[dict]:
    """One line per gruntly run of the task: what the child did, what it cost, why a run failed."""
    out = []
    for r in grs:
        g = r.get("gates") or {}
        out.append({"status": r.get("status"), "attempts": r.get("attempts"), "wall_s": r.get("wall_s"), "applied": r.get("applied"),
                    "verify": r.get("verify"), "child": r.get("child"), "child_trace": r.get("child_trace"),
                    "failed_gates": [k for k, v in g.items() if not (v is True or (isinstance(v, dict) and v.get("ok")))],
                    "reason": (r.get("failure_bundle") or {}).get("reason") or r.get("error"),
                    "files_touched": (r.get("diff_stat") or {}).get("paths"), "review_hint": r.get("review_hint"),
                    "warnings": r.get("warnings")})
    return out


def analyse(raw: str) -> dict:
    """Turns, cost, context and tool-output size from a stream-json transcript."""
    tool_bytes = peak = sessions = background = takeover = edits_total = 0
    first_call: dict = {}
    gcalls: dict[str, int] = {}
    seen_gruntly = False
    tools: dict[str, int] = {}
    result: dict = {}
    for line in raw.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = e.get("type")
        if t == "system" and e.get("subtype") == "init":
            sessions += 1  # a backgrounded run ends the turn; the conversation is replayed in a second session
        if t == "assistant":
            msg = e.get("message", {})
            u = msg.get("usage") or {}
            if not first_call and u:     # a session whose first call read nothing from the cache paid to write its whole prefix: a cold start
                first_call = {"cache_read": u.get("cache_read_input_tokens") or 0, "cache_write": u.get("cache_creation_input_tokens") or 0}
            peak = max(peak, (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                       + (u.get("cache_creation_input_tokens") or 0))
            for b in msg.get("content", []):
                if b.get("type") == "tool_use":
                    tools[b.get("name", "?")] = tools.get(b.get("name", "?"), 0) + 1
                    background += bool((b.get("input") or {}).get("run_in_background"))
                    if b.get("name") in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                        edits_total += 1
                    if b.get("name") == "Bash" and "gruntly" in str((b.get("input") or {}).get("command", "")):
                        seen_gruntly = True
                        cmdline = str((b.get("input") or {}).get("command", ""))
                        verb = re.search(r"gruntly\s+(agent-run|wait|continue|diff|discard|apply|doctor|stats|rules|mode|do|run)\b", cmdline)
                        kind = "continue" if "--continue" in cmdline else (verb.group(1) if verb else "other")
                        gcalls[kind] = gcalls.get(kind, 0) + 1
                    elif seen_gruntly and b.get("name") in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                        takeover += 1
        elif t == "user":
            for b in (e.get("message", {}).get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    tool_bytes += len(c if isinstance(c, str) else json.dumps(c))
        elif t == "result":
            result = e
    u = result.get("usage") or {}
    return {"cost_usd": round(result.get("total_cost_usd") or 0, 4), "turns": result.get("num_turns"),
            "reply": (result.get("result") or "")[:500], "tools": tools, "parent_edits_total": edits_total, "gruntly_calls": gcalls,
            "first_call": first_call, "cold_start": bool(first_call) and first_call["cache_read"] == 0,
            "model_usage": {m: {"input": v.get("inputTokens"), "output": v.get("outputTokens"), "cache_read": v.get("cacheReadInputTokens"),
                                "cache_write": v.get("cacheCreationInputTokens"), "cost_usd": v.get("costUSD")}
                            for m, v in (result.get("modelUsage") or {}).items()},
            "api_ms": result.get("duration_api_ms"), "sessions": sessions, "background_calls": background, "takeover_edits": takeover, "tool_output_bytes": tool_bytes, "peak_ctx": peak,
            "tokens": {"input": u.get("input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
                       "cache_read": u.get("cache_read_input_tokens", 0), "output": u.get("output_tokens", 0)}}


def gruntly_runs(work: Path) -> list[dict]:
    d = work / ".gruntly" / "runs"
    return [json.loads(p.read_text(encoding="utf8")) for p in sorted(d.glob("*/result.json"))] if d.exists() else []


VAGUE = yaml.safe_load((HERE / "vague_briefs.yaml").read_text(encoding="utf8"))


def run_one(task_dir: Path, arm: str, rep: int, a) -> dict:
    with tempfile.TemporaryDirectory(prefix="bench-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp) / "repo"
        spec = prepare(task_dir, work, a.harness, a.model, ('env_allow = ["PYTEST_ADDOPTS"]\n' if bucket(task_dir.name) == "R" else "")     # the parent's shell has it, so the child's must
                       + DO_TOML.get(arm, DO_TOML["gdA"] if arm == LEAN else "") + rate_limits_toml(a.rate_limits), a.provider,
                       getattr(a, "child_budget_s", 900), getattr(a, "child_idle_s", 300))
        if getattr(a, "vague", False) and task_dir.name in VAGUE:
            spec["brief"] = VAGUE[task_dir.name]     # intent only: no file, no function, no method
        cmd = [shutil.which("claude") or "claude", "-p", "--allowedTools", *TOOLS, "--output-format", "stream-json", "--verbose",
               "--max-turns", "40", "--max-budget-usd", str(a.budget_usd)]
        if a.parent_model:
            cmd += ["--model", a.parent_model]
        if arm == LEAN:
            from gruntly.agent import LEAN_PROMPT
            cmd = [c for c in cmd if c not in TOOLS]
            cmd[cmd.index("--allowedTools") + 1:cmd.index("--allowedTools") + 1] = ["Bash(gruntly *)"]
            cmd += ["--system-prompt", LEAN_PROMPT, "--tools", "Bash", "--strict-mcp-config", "--disable-slash-commands"]
        elif arm == SUBAGENT:
            cmd[cmd.index("--allowedTools") + 1:cmd.index("--allowedTools") + 1] = ["Agent"]
        elif arm == LEAN_ALONE:
            cmd = [c for c in cmd if c not in TOOLS]
            cmd[cmd.index("--allowedTools") + 1:cmd.index("--allowedTools") + 1] = ["Bash", "Read", "Edit", "Write"]
            cmd += ["--system-prompt", LEAN_ALONE_PROMPT, "--tools", "Bash,Read,Edit,Write", "--strict-mcp-config", "--disable-slash-commands"]
        elif arm != "alone":
            cmd += ["--plugin-dir", str(PLUGIN)]
        t0 = time.time()
        err = None
        if bucket(task_dir.name) == "R":            # real repositories: gruntly runs their tests on the interpreter the benchmark controls
            os.environ["GRUNTLY_PYTHON"] = sys.executable
        else:
            os.environ.pop("GRUNTLY_PYTHON", None)
        try:
            env = ({**os.environ, "BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "600000"} if arm == LEAN else
                   {**os.environ, "BASH_MAX_TIMEOUT_MS": "3600000"} if arm == SUPERVISED else None)   # one blocking call, not many waits
            p = sh(cmd, work, timeout=7200 if arm == SUPERVISED else max(2400, 2 * getattr(a, "child_budget_s", 900) + 600), input=prompt_for(arm, spec), env=env)  # stdin: the Windows .cmd shim mangles multi-line args
            raw = p.stdout
            if not raw.strip():
                err = (p.stderr or "empty output")[-300:]
        except subprocess.TimeoutExpired:
            raw, err = "", "timeout"
        wall = round(time.time() - t0)
        runs_dir = HERE / (a.runs_dir or "runs")
        runs_dir.mkdir(exist_ok=True)
        (runs_dir / f"{task_dir.name}.{arm}.{rep}.jsonl").write_text(raw, encoding="utf8")
        info = analyse(raw)
        grs = gruntly_runs(work)
        passed = judge(task_dir, work)
        detail = judge_detail()
        final = save_artifacts(work, runs_dir, f"{task_dir.name}.{arm}.{rep}")
        gsum = gruntly_summary(grs)
        gwall = sum(g.get("wall_s") or 0 for g in gsum)
        return {"task": task_dir.name, "bucket": bucket(task_dir.name), "arm": arm, "rep": rep, "passed": passed,
                "judge": detail, "final_patch": final, "gruntly": gsum,
                "parent_model": a.parent_model, "child_harness": a.harness if arm != "alone" else None,
                "child_model": a.model if arm != "alone" else None,
                "gruntly_wall_s": gwall, "parent_wall_s": max(wall - gwall, 0),       # wall = whole session; the rest is the parent thinking, reading, replying
                "wall_s": wall, "error": err, **info, "gruntly_status": [r["status"] for r in grs],
                "gruntly_applied": [r.get("applied") for r in grs], "gruntly_attempts": [r["attempts"] for r in grs],
                "gruntly_result_chars": [len(json.dumps(r)) for r in grs],
                "child_tokens": sum(r.get("child_tokens") or 0 for r in grs),
                "child_cost_usd": round(sum((r.get("child") or {}).get("cost_usd") or 0 for r in grs), 5),   # a Claude child is paid
                # reviewer calls made by gruntly outside the parent's session are paid too: count them
                "reviewer_cost_usd": round(sum(json.loads(p.read_text(encoding="utf8")).get("reviewer_cost_usd", 0)
                                               for p in (work / ".gruntly" / "supervised").glob("*/costs.json")), 5)}


def write_meta(path: Path, a) -> None:
    """Everything needed to read the rows later: what was run, on which code, with which tools. One entry per invocation."""
    def out(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, encoding="utf8", timeout=30, cwd=HERE.parent).stdout.strip()
        except Exception:  # noqa: BLE001
            return "?"
    try:
        plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf8")).get("version")
    except Exception:  # noqa: BLE001
        plugin = None
    entry = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "argv": sys.argv[1:], "args": vars(a),
             "gruntly_commit": out("git", "rev-parse", "--short", "HEAD"), "tree_dirty": bool(out("git", "status", "--porcelain", "--", "src", "bench", "plugin")),
             "claude": out(shutil.which("claude") or "claude", "--version"), "python": sys.version.split()[0], "plugin_version": plugin,
             "pytest": out(sys.executable, "-m", "pytest", "--version"),
             "prices_per_mtok": {"sonnet-5.5": {"input": 2.0, "output": 10.0, "cache_read": 0.10, "cache_write_1h": 4.0}},
             "note": "costs are Claude Code's own total_cost_usd (parent) and the CLI's total_cost_usd per child attempt; API-equivalent dollars"}
    old = json.loads(path.read_text(encoding="utf8")) if path.exists() else []
    path.write_text(json.dumps(old + [entry], indent=1), encoding="utf8")


def mean(xs):
    return statistics.fmean(xs) if xs else 0.0


FLOOR = 0.045                 # a fresh `claude -p` session pays this before it does anything (docs/investigation-2026-11-11.md)
CAPS = (0.05, 0.10, 0.20, 0.50, 1.00)


def total(r: dict) -> float:
    """What the person pays for one run: the parent session plus the reviewers gruntly called outside it. The child is local or
    the person's own hosted key and is never counted as money."""
    return r["cost_usd"] + (r.get("reviewer_cost_usd") or 0) + (r.get("child_cost_usd") or 0)


def cost_of_pass(rs: list[dict]) -> str:
    """Mean cost per run divided by the pass rate: the expected cost of one correct solution (a false pass counts as no pass)."""
    rate = mean([r["passed"] for r in rs])
    return f"{mean([total(r) for r in rs]) / rate:.3f}" if rate else "inf"


def report(rows: list[dict], meta: dict) -> str:
    arms = [x for x in ("alone", "forced", "policy", "planner", "supervised", "subagent", "gd", "gdA", "gdAB", "lean", "lean_alone") if any(r["arm"] == x for r in rows)]
    L = ["# gruntly benchmark (v2)", "",
         f"Local child: `{meta['harness']}` / `{meta['model']}` at 32k context. Parent: Claude Code ({meta.get('parent_model') or 'default model'}). "
         f"Run {time.strftime('%Y-%m-%d')}. Pass = hidden tests (never shown to the parent or the child) pass afterwards. "
         "S = ten small tasks the parent solves in ~4 turns; L = three larger tasks (six bugs, a 15-file rename, a CLI feature); R = real fix commits of public repositories (hidden tests = the fix's own). "
         "Arms: `alone`; `forced` (told to delegate through the one-call flow); `policy` (may delegate if the skill's triage rule says so).", "",
         "## Totals by bucket (means over tasks and repetitions)", "",
         "| bucket | arm | runs | pass rate | cost $/run | reviewer $ | vs alone | marginal $ (after the $0.045 floor) | vs alone, marginal | cost of a pass $ | turns | takeover edits | session splits | wall s | parent output tok | tool-output KB in context | delegated | child tok |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for b in ("S", "L", "R"):
        base = [total(r) for r in rows if r["bucket"] == b and r["arm"] == "alone"]
        for arm in arms:
            rs = [r for r in rows if r["bucket"] == b and r["arm"] == arm]
            if not rs:
                continue
            rel = f"{mean([total(r) for r in rs]) / mean(base) - 1:+.0%}" if base and arm != "alone" else "-"
            marg = mean([total(r) - FLOOR for r in rs])
            marg_rel = (f"{marg / (mean(base) - FLOOR) - 1:+.0%}" if base and arm != "alone" and mean(base) > FLOOR else "-")
            deleg = sum(1 for r in rs if r["gruntly_status"])
            L.append(f"| {b} | {arm} | {len(rs)} | {mean([r['passed'] for r in rs]):.0%} | {mean([total(r) for r in rs]):.3f} | "
                     f"{mean([r.get('reviewer_cost_usd') or 0 for r in rs]):.4f} | {rel} | {marg:.3f} | {marg_rel} | {cost_of_pass(rs)} | "
                     f"{mean([r['turns'] or 0 for r in rs]):.1f} | {mean([r.get('takeover_edits', 0) for r in rs]):.1f} | "
                     f"{mean([max(0, r.get('sessions', 1) - 1) for r in rs]):.1f} | "
                     f"{mean([r['wall_s'] for r in rs]):.0f} | {mean([r['tokens']['output'] for r in rs]):.0f} | {mean([r['tool_output_bytes'] for r in rs]) / 1024:.1f} | "
                     f"{deleg}/{len(rs)} | {sum(r['child_tokens'] for r in rs) or '-'} |")
    L += ["", "## Share of runs that passed within a cost cap (parent + reviewers per run; a run over the cap counts as not solved)", "",
          "| arm | runs | " + " | ".join(f"<= ${c:.2f}" for c in CAPS) + " |", "|---|---|" + "---|" * len(CAPS)]
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        L.append(f"| {arm} | {len(rs)} | " + " | ".join(f"{sum(1 for r in rs if r['passed'] and total(r) <= c) / len(rs):.0%}" for c in CAPS) + " |")
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
            L.append(f"| {task} | {arm} | {sum(r['passed'] for r in rs)}/{len(rs)} | {mean([total(r) for r in rs]):.3f} | "
                     f"{mean([r['turns'] or 0 for r in rs]):.1f} | {mean([r['wall_s'] for r in rs]):.0f} | {g} | {fp or '-'} |")
    errs = [r for r in rows if r.get("error")]
    if errs:
        L += ["", "Errors: " + "; ".join(f"{r['task']}/{r['arm']}#{r['rep']}: {r['error']}" for r in errs)]
    L += ["", "Accounting: cost = Claude Code's own `total_cost_usd` for the whole session (cache reads included, so any takeover "
          "after an escalation is counted) plus the reviewers gruntly called outside it. Marginal = cost minus the $0.045 every fresh "
          "`claude -p` session pays before doing anything (it is the same in every arm, so it hides the differences). Cost of a pass = "
          "mean cost / pass rate. Takeover edits = the parent's own Edit/Write calls after its first gruntly call. "
          "Local child tokens are free of paid cost but cost wall time. "
          "False pass = gruntly reported `passed` but the hidden tests failed. Transcripts are in `bench/runs/`."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", default="opencode")
    ap.add_argument("--model", default="qwen/qwen3.5-9b")
    ap.add_argument("--runs-dir", default="", help="folder under bench/ for the transcripts (default: runs)")
    ap.add_argument("--vague", action="store_true", help="use bench/vague_briefs.yaml (intent only) where a task has one")
    ap.add_argument("--provider", default="", help="hosted provider for the child (e.g. nvidia); default: the local server")
    ap.add_argument("--parent-model", default="sonnet", help="Claude model for the parent (alias or id)")
    ap.add_argument("--child-budget-s", type=int, default=900, help="wall-clock seconds one child run may take (a slow hosted model needs more)")
    ap.add_argument("--child-idle-s", type=int, default=300, help="seconds without any child progress before gruntly gives up on it")
    ap.add_argument("--rate-limits", default="",
                    help="override the hosted provider's preset limits for the child, e.g. rpm=10,tpm=250000 (the Gemini preset is for Gemma)")
    ap.add_argument("--tasks", default="")
    ap.add_argument("--real", action="store_true", help="run the tasks from real repositories (bench/tasks-real, see real_tasks.py)")
    ap.add_argument("--arms", default="alone,forced,policy")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--budget-usd", type=float, default=1.5, help="per-run cap for the parent")
    ap.add_argument("--max-total-usd", type=float, default=0,
                    help="stop before a run whose expected cost (the dearest run so far, at least $0.15) would pass this total; 0 = no cap")
    ap.add_argument("--resume", action="store_true", help="continue from the saved .json next to --out")
    ap.add_argument("--report-only", action="store_true", help="re-render the saved .json next to --out with the current report; run nothing")
    ap.add_argument("--out", default=str(HERE.parent / "docs" / "benchmarks" / "benchmark-v2.md"))
    a = ap.parse_args()
    names = [n for n in a.tasks.split(",") if n] or sorted(p.name for p in (HERE / "tasks").iterdir() if p.is_dir())
    if a.real:        # the tasks from real repositories, without the ones whose problem statement is a one-line changelog entry
        # click's pytest config turns warnings into errors, and the pytest on this machine (9.2) deprecates something its older tests
        # do: the unmodified suite then fails to collect (tests/test_basic.py), and gruntly's whole-suite gate could never pass. Every
        # arm, the hidden-test judge and gruntly's gate see the same pytest options, set here.
        opt = "-W ignore::pytest.PytestRemovedIn10Warning"
        os.environ["PYTEST_ADDOPTS"] = (os.environ.get("PYTEST_ADDOPTS", "") + " " + opt).strip()
        wanted = {n for n in a.tasks.split(",") if n}            # --tasks narrows the real tasks too
        names = sorted(p.name for p in (HERE / "tasks-real").iterdir()
                       if p.is_dir() and not yaml.safe_load((p / "task.yaml").read_text(encoding="utf8")).get("vague")
                       and (not wanted or p.name in wanted))
    raw = Path(a.out).with_suffix(".json")
    if a.report_only:
        Path(a.out).write_text(report(json.loads(raw.read_text(encoding="utf8")), vars(a)), encoding="utf8")
        print(f"wrote {a.out}")
        return
    rows = json.loads(raw.read_text(encoding="utf8")) if raw.exists() and a.resume else []
    write_meta(Path(str(raw)[:-5] + ".meta.json"), a)
    done = {(r["task"], r["arm"], r["rep"]) for r in rows}
    stopped = False
    for rep in range(1, a.reps + 1):
        for n in names:
            for arm in a.arms.split(","):
                if (n, arm, rep) in done:
                    continue
                spent = sum(total(r) for r in rows)
                expect = max([total(r) for r in rows] + [0.15])
                if a.max_total_usd and spent + expect > a.max_total_usd:
                    print(f"stopped: ${spent:.2f} spent, the next run (about ${expect:.2f}) would pass --max-total-usd {a.max_total_usd}", flush=True)
                    stopped = True
                    break
                print(f"[{n} / {arm} / rep {rep}] ...", flush=True)
                r = run_one(task_dir_of(n), arm, rep, a)
                rows.append(r)
                print(f"  pass={r['passed']} ${total(r):.4f} (child ${r.get('child_cost_usd') or 0:.4f}) turns={r['turns']} wall={r['wall_s']}s gruntly={r['gruntly_status']}", flush=True)
                raw.write_text(json.dumps(rows, indent=1), encoding="utf8")
                Path(a.out).write_text(report(rows, vars(a)), encoding="utf8")
            if stopped:
                break
        if stopped:
            break
    print(f"wrote {a.out}  (total ${sum(total(r) for r in rows):.2f})")


if __name__ == "__main__":
    main()
