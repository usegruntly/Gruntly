"""`gruntly demo`: see what gruntly does around a child, in two minutes, with nothing to set up.

Offline (the default) a stand-in child plays the model, so there is no model server, no API key and no network: gruntly builds a toy repository in a temporary folder and
runs three tasks through the real runner, gates and result block. 1. A child fixes the bug. 2. A child "passes" by rewriting the test. 3. A child writes into the
person's own checkout (issue #6), and `gruntly restore` puts it back. It exits non-zero if any of them does not behave as designed, so it also works as a smoke test of an install.

`--live` runs the first task with the child, model and provider you configured (`gruntly setup`), to check the whole chain end to end.
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import time
from pathlib import Path

from . import restore as restoremod, result as resmod, runner, worktree as wtmod
from .spec import build_spec
from .store import force_rmtree

CALC = "def add(a, b):\n    return a - b\n"
TEST = ("from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\n"
        "if __name__ == \"__main__\":\n    test_add()\n    print(\"ok\")\n")
BRIEF = "Fix add() in calc.py so test_calc.py passes. Do not edit the tests."


def _spec(child_cmd=None) -> dict:
    raw = {"brief": BRIEF, "allowed_paths": ["calc.py"], "max_attempts": 1, "budget_s": 120, "no_progress_s": 60,
           "acceptance": [{"cmd": f'"{sys.executable}" test_calc.py', "timeout_s": 60}]}
    if child_cmd:
        raw.update({"harness": "generic", "child_cmd": child_cmd})
    return raw


@contextlib.contextmanager
def _env(**over):
    old = {k: os.environ.get(k) for k in over}
    os.environ.update(over)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _toy_repo(base: Path) -> Path:
    repo = base / "toy"
    repo.mkdir()
    (repo / "calc.py").write_text(CALC)
    (repo / "test_calc.py").write_text(TEST)
    wtmod.git(["init", "-q"], repo)
    wtmod.git(["add", "-A"], repo)
    wtmod.git(["commit", "-qm", "toy repo with a bug in add()"], repo, env=wtmod.IDENT)
    return repo


def _gates(res: dict) -> str:
    return " | ".join(f"{n} {'ok' if v is True else 'FAILED'}" for n, v in res["gates"].items())


def _run(repo: Path, raw: dict) -> tuple[dict, str, Path]:
    root = wtmod.preflight(repo)
    rid = runner.prepare(build_spec(raw, root), root)
    return runner.execute(root, rid), rid, root


def _say(text: str = "") -> None:
    print(text, flush=True)


def run(live: bool = False, keep: bool = False) -> int:
    _say("gruntly demo: " + ("your configured child and model, on a toy repository." if live else
                             "no model, no key, no network. A stand-in child plays the model, so you can see what gruntly does around it."))
    base = Path(tempfile.mkdtemp(prefix="gruntly-demo-"))
    problems: list[str] = []
    try:
        repo = _toy_repo(base)
        _say(f"toy repository: {repo} (add() subtracts; one test fails)\n")
        env = {"GRUNTLY_STATE_DIR": str(base / "state")}
        if not live:
            env["GRUNTLY_CONFIG_DIR"] = str(base / "config")        # your own settings must not change what the demo shows
        with _env(**env):
            if live:
                problems += _live(repo)
            else:
                problems += _offline(repo)
    except Exception as e:  # noqa: BLE001
        problems.append(f"the demo itself failed: {e}")
    finally:
        if keep:
            _say(f"\nkept: {base}")
        else:
            force_rmtree(base)
    if problems:
        _say("\nNOT as designed:\n  " + "\n  ".join(problems))
        return 1
    if live:
        _say("\nThe whole chain works: model, child harness, gates and result. Use it on a real task: `gruntly run --spec spec.yaml`, or from your agent (see the README).")
    else:
        _say("\nAll three behaved as designed. Next: `gruntly setup` picks your model and child, then `gruntly demo --live` runs the first task with them.")
    return 0


def _offline(repo: Path) -> list[str]:
    problems: list[str] = []
    cmd = lambda scenario: [sys.executable, "-m", "gruntly.demo_child", scenario, "{prompt}"]      # noqa: E731

    _say("1/3  A child fixes the bug")
    res, rid, root = _run(repo, _spec(cmd("fix")))
    stat = res.get("diff_stat", {})
    _say(f"     gates: {_gates(res)}")
    _say(f"     result: {res['status']} ({stat.get('files', '?')} file, +{stat.get('insertions', '?')} -{stat.get('deletions', '?')}); "
         f"{resmod.size(res)} characters go back to your agent. Nothing is in your tree until you `gruntly apply {rid}`.")
    if res["status"] != "passed":
        problems.append(f"task 1 should pass, got {res['status']}")

    _say("\n2/3  A child 'passes' by rewriting the test instead of fixing the code")
    res, rid, root = _run(repo, _spec(cmd("weaken")))
    _say(f"     gates: {_gates(res)}")
    findings = res["gates"].get("test_weakening", {}).get("findings", []) if isinstance(res["gates"].get("test_weakening"), dict) else []
    _say(f"     result: {res['status']}. The test would have passed, but gruntly saw it: {'; '.join(findings) or 'nothing?'}")
    if res["status"] != "escalate" or not findings:
        problems.append(f"task 2 should be stopped by the test_weakening gate, got {res['status']} with gates {_gates(res)}")

    _say("\n3/3  A child writes into your own working tree instead of its worktree")
    res, rid, root = _run(repo, _spec(cmd("leak")))
    violations = res["gates"].get("scope", {}).get("violations", []) if isinstance(res["gates"].get("scope"), dict) else []
    _say(f"     gates: {_gates(res)}")
    _say(f"     result: {res['status']}. {'; '.join(violations) or 'nothing?'}")
    leaked = (repo / "notes.txt").exists()
    _say(f"     the stray file is in your tree: {leaked}. `gruntly restore {rid}` puts your tree back, touching only files still as the child left them:")
    done = restoremod.restore(root, rid)
    _say(f"     restored: {', '.join(done.get('restored', [])) or 'nothing?'}; notes.txt is now in your tree: {(repo / 'notes.txt').exists()}")
    if res["status"] != "escalate" or not leaked or done.get("restored") != ["notes.txt"] or (repo / "notes.txt").exists():
        problems.append("task 3 should be stopped by the scope gate and fully restored")
    return problems


def _live(repo: Path) -> list[str]:
    _say("task: " + BRIEF)
    t0 = time.monotonic()
    res, rid, _ = _run(repo, {**_spec(), "max_attempts": 2, "budget_s": 600, "no_progress_s": 300})
    _say(f"gates: {_gates(res)}" if res.get("gates") else "gates: not reached")
    _say(f"result: {res['status']} in {round(time.monotonic() - t0)} s ({resmod.size(res)} characters back to your agent)")
    if res["status"] == "passed":
        return []
    reason = res.get("error") or (res.get("failure_bundle") or {}).get("reason") or "no reason given"
    return [f"the run ended {res['status']}: {reason}. Check `gruntly doctor`, and that `gruntly setup` has picked a child and a model that work"]
