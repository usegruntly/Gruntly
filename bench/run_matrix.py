"""The benchmark matrix: any parent harness x any child harness x any provider, one results store, one report.

    python bench/run_matrix.py --cells bench/cells.example.toml --tasks slugify,retry --reps 1             # a dry run: the plan, what is paid, nothing runs
    python bench/run_matrix.py --cells cells.toml --tasks slugify --reps 2 --run --max-usd 2.00 --yes-paid   # run it

Each cell of the file is one setup (a `[[cell]]` table):

    [[cell]]
    name = "codex-lean-qwen-local"
    parent = "codex"                      # any registered parent harness (gruntly harness matrix), or "claude"
    mode = "delegating"                   # or "working": the parent does the job itself, no gruntly (the baseline)
    parent_model = "gpt-x"
    parent_provider = "openai"            # a catalog provider, or omit to use the harness's own login
    child_harness = "opencode"            # ignored for a working cell
    child_model = "qwen3.5-9b"
    child_provider = "local"              # "local" = the local model server

Nothing is spent unless `--run` is given, and a cell that is PAID (a parent on your own login or a hosted non-free provider, a Claude child) needs
`--yes-paid` as well. `--max-usd` stops the run before the next one once the dollars already measured reach it (a run whose price is unknown counts
as zero toward the cap and is listed as unknown, never silently priced). Parent tokens come from the harness's own output, dollars from the harness
when it reports them and otherwise from `gruntly/pricing.py` (the provider's report, a price table, or unknown); the child's come from gruntly's own
records. Every run is one JSON line in `<out>/results.jsonl` and its raw material is kept beside it, so any figure can be recomputed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import run_bench as rb  # noqa: E402

from gruntly import parents, pricing, providers  # noqa: E402
from gruntly.parents import base, prompts  # noqa: E402
from gruntly.usage import Usage  # noqa: E402

CELL_KEYS = {"name", "parent", "mode", "parent_model", "parent_provider", "child_harness", "child_model", "child_provider"}


def load_cells(path: Path) -> list[dict]:
    data = tomllib.loads(Path(path).read_text(encoding="utf8"))
    cells = data.get("cell") or []
    if not cells:
        raise SystemExit(f"{path}: no [[cell]] tables")
    out = []
    for i, c in enumerate(cells, 1):
        unknown = set(c) - CELL_KEYS
        if unknown:
            raise SystemExit(f"{path}: cell {i} has unknown field(s) {sorted(unknown)}; known: {sorted(CELL_KEYS)}")
        c = {"mode": "delegating", "child_harness": "opencode", **c}
        c.setdefault("name", f"{c.get('parent')}-{c['mode']}-{i}")
        if c.get("parent") not in parents.names():
            raise SystemExit(f"{path}: cell {c['name']}: unknown parent {c.get('parent')!r}; known: {', '.join(parents.names())}")
        if c["mode"] not in ("delegating", "working"):
            raise SystemExit(f"{path}: cell {c['name']}: mode must be delegating or working")
        caps = parents.get_parent(c["parent"]).capabilities()
        if c["mode"] not in caps.modes:
            raise SystemExit(f"{path}: cell {c['name']}: {c['parent']} cannot run in {c['mode']} mode")
        for key in ("parent_provider", "child_provider"):
            pv = c.get(key)
            if pv and pv != "local" and pv not in providers.ALL:
                raise SystemExit(f"{path}: cell {c['name']}: unknown {key} {pv!r}; known: local, {', '.join(providers.ALL)}")
        out.append(c)
    names = [c["name"] for c in out]
    if len(set(names)) != len(names):
        raise SystemExit(f"{path}: cell names must be unique")
    return out


def hosted(provider: str | None) -> bool:
    return bool(provider) and provider != "local" and providers.ALL[provider].kind == "hosted"


def paid_reasons(c: dict) -> list[str]:
    """Why a cell may cost money, or an empty list. Only your own local server is not: a hosted provider counts even when it has a free tier,
    because a free tier is limited and covers some models only (OpenRouter's free models, for one), so it is no guarantee of zero cost."""
    why = []
    pp = c.get("parent_provider")
    if not pp:
        why.append(f"the {c['parent']} parent runs on your own login")
    elif hosted(pp):
        why.append(f"the parent uses {pp} (hosted: a free tier is not a guarantee of no cost)")
    if c["mode"] == "delegating":
        cp = c.get("child_provider") or "local"
        if c["child_harness"] == "claude":
            why.append("the child is Claude Code (your Claude usage)")
        elif hosted(cp):
            why.append(f"the child uses {cp} (hosted: a free tier is not a guarantee of no cost)")
    return why


def plan(cells: list[dict], tasks: list[str], reps: int) -> list[dict]:
    return [{"cell": c, "task": t, "rep": r} for c in cells for t in tasks for r in range(reps)]


def parent_cost(outcome, provider: str | None, model: str | None):
    """(dollars or None, source): what the harness reported, else the price table / provider report, else unknown (never zero)."""
    if outcome.cost_usd is not None:
        return outcome.cost_usd, "reported by the harness"
    if outcome.usage is None:
        return None, "unknown: the harness reported no usage"
    p = providers.ALL.get(provider or "")
    if not provider:
        return None, "unknown: the harness's own login has no price here"
    c = pricing.cost(outcome.usage, provider, model, p.kind if p else "hosted")
    return c.usd, c.source


def run_one(task_dir: Path, cell: dict, rep: int, out: Path, timeout_s: int = 2400) -> dict:
    stem = f"{cell['name']}.{task_dir.name}.{rep}"
    with tempfile.TemporaryDirectory(prefix="matrix-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp) / "repo"
        child_provider = cell.get("child_provider") or "local"
        spec = rb.prepare(task_dir, work, cell["child_harness"], cell.get("child_model") or "default", "", "" if child_provider == "local" else child_provider)
        task = rb.prompt_for("lean" if cell["mode"] == "delegating" else "alone", spec)
        if cell["mode"] == "working":
            task = prompts.working_task(task)
        env = {"GRUNTLY_STATE_DIR": str(Path(tmp) / "state"), "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
               "BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "600000"}
        if rb.bucket(task_dir.name) == "R":
            env["GRUNTLY_PYTHON"] = sys.executable
        adapter = parents.get_parent(cell["parent"])
        t0 = time.time()
        res = base.run(adapter, task, cell["mode"], cell.get("parent_model"), cell.get("parent_provider") or None, cwd=work, timeout_s=timeout_s, env=env)
        wall = round(time.time() - t0)
        grs = rb.gruntly_runs(work)
        passed = rb.judge(task_dir, work)
        detail = rb.judge_detail()
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{stem}.parent.out").write_text((res.stdout or "") + ("\n--- stderr ---\n" + res.stderr if res.stderr else ""), encoding="utf8")
        final = rb.save_artifacts(work, out, stem)
        gsum = rb.gruntly_summary(grs)
        usd, source = parent_cost(res.outcome, cell.get("parent_provider"), cell.get("parent_model"))
        child_usd = round(sum((r.get("child") or {}).get("cost_usd") or 0 for r in grs), 6)
        child_unknown = sum(1 for r in grs if (r.get("child") or {}).get("cost_unknown"))
        u = res.outcome.usage
        return {"cell": cell["name"], "task": task_dir.name, "bucket": rb.bucket(task_dir.name), "rep": rep, "passed": passed, "judge": detail,
                "mode": cell["mode"], "parent": cell["parent"], "parent_model": cell.get("parent_model"), "parent_provider": cell.get("parent_provider"),
                "child_harness": cell["child_harness"] if cell["mode"] == "delegating" else None, "child_model": cell.get("child_model"), "child_provider": child_provider,
                "wall_s": wall, "parent_error": res.outcome.is_error, "parent_turns": res.outcome.turns, "parent_reply": res.outcome.final_message[:300],
                "parent_usage": ({"prompt": u.prompt, "completion": u.completion, "cached": u.cached, "requests": u.requests} if u else None),
                "parent_usd": usd, "parent_cost_source": source, "child_usd": child_usd, "child_cost_unknown": child_unknown,
                "child_tokens": sum(r.get("child_tokens") or 0 for r in grs), "gruntly_status": [r["status"] for r in grs],
                "usd_total": round((usd or 0) + child_usd, 6), "usd_complete": usd is not None and not child_unknown, "final_patch": final,
                "notes": res.command.notes if res.command else []}


def report(rows: list[dict]) -> str:
    cells = list(dict.fromkeys(r["cell"] for r in rows))
    out = ["| cell | runs | passed | parent tokens (mean) | parent $ (mean) | child $ (mean) | wall s (mean) | $ per correct task |", "|---|---|---|---|---|---|---|---|"]
    for c in cells:
        rs = [r for r in rows if r["cell"] == c]
        ok = [r for r in rs if r["passed"]]
        tok = [((r["parent_usage"] or {}).get("prompt", 0) + (r["parent_usage"] or {}).get("completion", 0)) for r in rs if r["parent_usage"]]
        pu = [r["parent_usd"] for r in rs if r["parent_usd"] is not None]
        complete = all(r["usd_complete"] for r in rs)
        per_correct = (f"${sum(r['usd_total'] for r in rs) / len(ok):.3f}" if ok else "-") + ("" if complete else " (lower bound: some prices unknown)")
        out.append(f"| {c} | {len(rs)} | {len(ok)}/{len(rs)} | {round(sum(tok) / len(tok)) if tok else '?'} | "
                   f"{('$%.4f' % (sum(pu) / len(pu))) if pu else 'unknown'} | ${sum(r['child_usd'] for r in rs) / len(rs):.4f} | "
                   f"{round(sum(r['wall_s'] for r in rs) / len(rs))} | {per_correct} |")
    out += ["", "Dollars: a parent's come from the harness when it reports them, else the provider's report or the price table, else UNKNOWN (counted as zero in the "
            "totals, which then say lower bound). n is small: read these as a smoke test, not a ranking."]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cells", required=True, help="a TOML file of [[cell]] tables")
    ap.add_argument("--tasks", required=True, help="comma-separated task names (bench/tasks, bench/tasks-real)")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--out", default=str(ROOT / "docs" / "benchmarks" / "matrix"))
    ap.add_argument("--run", action="store_true", help="actually run (the default only prints the plan)")
    ap.add_argument("--yes-paid", action="store_true", help="allow cells that cost money")
    ap.add_argument("--max-usd", type=float, default=None, help="stop before the next run once the measured dollars reach this")
    ap.add_argument("--resume", action="store_true", help="skip runs already in results.jsonl")
    a = ap.parse_args()
    cells = load_cells(Path(a.cells))
    tasks = [t.strip() for t in a.tasks.split(",") if t.strip()]
    for t in tasks:
        if not rb.task_dir_of(t).is_dir():
            raise SystemExit(f"unknown task {t!r}")
    runs = plan(cells, tasks, a.reps)
    out = Path(a.out)
    store = out / "results.jsonl"
    done = {(r["cell"], r["task"], r["rep"]) for r in map(json.loads, store.read_text(encoding="utf8").splitlines())} if a.resume and store.is_file() else set()
    print(f"{len(cells)} cell(s) x {len(tasks)} task(s) x {a.reps} rep(s) = {len(runs)} run(s)" + (f", {len(done)} already done" if done else ""))
    paid = False
    for c in cells:
        why = paid_reasons(c)
        paid = paid or bool(why)
        print(f"  {c['name']}: {c['parent']} ({c['mode']}) -> " + (f"{c['child_harness']} / {c.get('child_provider') or 'local'}" if c["mode"] == "delegating" else "no child")
              + ("   PAID: " + "; ".join(why) if why else "   not paid (free tier or local)"))
    if not a.run:
        print("\nDry run: nothing was started. Add --run" + (" --yes-paid --max-usd N" if paid else "") + " to run it.")
        return 0
    if paid and not (a.yes_paid and a.max_usd is not None):
        raise SystemExit("this plan has paid cells: pass --yes-paid and --max-usd N (a stated cap) to run it")
    spent, rows = 0.0, []
    for r in runs:
        key = (r["cell"]["name"], r["task"], r["rep"])
        if key in done:
            continue
        if a.max_usd is not None and spent >= a.max_usd:
            print(f"stopped: the measured dollars (${spent:.4f}) reached the cap ${a.max_usd:.2f}")
            break
        row = run_one(rb.task_dir_of(r["task"]), r["cell"], r["rep"], out)
        spent += row["usd_total"]
        rows.append(row)
        out.mkdir(parents=True, exist_ok=True)
        with store.open("a", encoding="utf8") as f:
            f.write(json.dumps(row) + "\n")
        print(f"  {key[0]} / {key[1]} / {key[2]}: {'PASS' if row['passed'] else 'fail'}  ${row['usd_total']:.4f}{'' if row['usd_complete'] else ' (incomplete)'}  {row['wall_s']} s")
    allrows = [json.loads(x) for x in store.read_text(encoding="utf8").splitlines()] if store.is_file() else []
    (out / "report.md").write_text(report(allrows) + "\n", encoding="utf8")
    print("\n" + report(allrows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
