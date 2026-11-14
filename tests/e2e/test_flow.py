"""The optimized parent flow: one-call apply, red-before-green, context preflight, injection boundary."""
import json
import sys

import pytest

from gruntly import runner, worktree
from gruntly.spec import build_spec

SECRET = "sk-test1234567890abcdefghijklmnop"


def test_apply_on_pass_lands_patch_and_cleans_up(repo, run_task, make_spec):
    res, root = run_task(make_spec("pass", apply_on_pass=True))
    assert res["status"] == "passed" and res["applied"] is True and res["verify"] == "unchanged"
    assert res["next"] == []
    assert "a + b" in (repo / "calc.py").read_text()
    assert not (root / ".gruntly" / "worktrees" / res["run_id"]).exists()
    assert worktree.git(["log", "--oneline"], repo).stdout.count("\n") == 1  # never commits
    assert len(json.dumps(res)) < 600


def test_apply_reverifies_when_the_tree_moved_since_the_run(repo, run_task, make_spec, capsys, monkeypatch):
    """The parent edited files between the run and apply, so acceptance is re-run where the patch lands."""
    from gruntly import cli
    res, _ = run_task(make_spec("pass", allowed_paths=["calc.py"]))
    (repo / "notes.txt").write_text("edited after the run\n")
    monkeypatch.chdir(repo)
    cli.main(["apply", res["run_id"]])
    out = json.loads(capsys.readouterr().out)
    assert out["applied"] is True and out["verify"] == "ok"


def test_apply_reverses_the_patch_when_main_tree_verification_fails(repo, run_task, make_spec, capsys, monkeypatch):
    from gruntly import cli
    res, _ = run_task(make_spec("pass", allowed_paths=["calc.py"]))
    # after the run, the tree the patch will land on changes so that acceptance fails there
    (repo / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n    assert False\n")
    monkeypatch.chdir(repo)
    cli.main(["apply", res["run_id"]])
    out = json.loads(capsys.readouterr().out)
    assert out["applied"] is False and out["verify"] == "failed"
    assert (repo / "calc.py").read_text().count("a - b") == 1  # reversed, not left half-applied


def test_failed_run_is_never_applied(repo, run_task, make_spec):
    res, _ = run_task(make_spec("no_fix", apply_on_pass=True, max_attempts=1))
    assert res["status"] == "escalate" and "applied" not in res
    assert "a - b" in (repo / "calc.py").read_text()


def test_a_spec_from_an_old_run_record_that_still_names_a_holdout_is_read_without_an_error(repo, make_spec):
    """The holdout option was removed; run records and specs written before that must still load (the field is ignored)."""
    root = worktree.preflight(repo)
    spec = build_spec(make_spec("pass", holdout={"files": ["holdout_calc.py"], "cmd": "pytest -q"}, hide=["x.py"], allowed_paths=["calc.py"]), root)
    assert not hasattr(spec, "holdout") and not hasattr(spec, "hide")


def test_red_before_green_warns_when_acceptance_already_passes(repo, run_task, make_spec):
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    worktree.git(["commit", "-qam", "already fixed"], repo)
    res, _ = run_task(make_spec("pass", max_attempts=1))
    assert any("already passes" in w for w in res["warnings"])
    assert any("weak acceptance" in h for h in res["review_hint"])


def test_a_healthy_pass_has_no_review_hint(repo, run_task, make_spec):
    res, _ = run_task(make_spec("pass"))
    assert "review_hint" not in res and "warnings" not in res


def test_regression_gate_runs_the_wider_suite(repo, run_task, make_spec):
    (repo / "test_other.py").write_text("def test_other():\n    assert False\n")
    worktree.git(["add", "-A"], repo)
    worktree.git(["commit", "-qm", "broken suite"], repo)
    res, _ = run_task(make_spec("pass", max_attempts=1, gates={"regression": f'"{sys.executable}" -m pytest -q'},
                                acceptance=[{"cmd": f'"{sys.executable}" -m pytest -q test_calc.py'}]))
    assert res["gates"]["acceptance"] is True and res["gates"]["regression"]["ok"] is False
    assert res["status"] == "escalate"


def test_child_text_is_confined_to_the_untrusted_key(repo, run_task, make_spec):
    res, _ = run_task(make_spec("inject", max_attempts=1))
    outside = json.dumps({k: v for k, v in res.items() if k != "untrusted"})
    assert "IGNORE PREVIOUS INSTRUCTIONS" not in outside
    assert "IGNORE PREVIOUS INSTRUCTIONS" in json.dumps(res["untrusted"])
    assert SECRET not in json.dumps(res)


def test_small_context_is_refused_before_any_attempt(repo, make_spec, monkeypatch):
    from gruntly import doctor
    from gruntly.adapters.base import Detection
    monkeypatch.setattr(doctor, "probe_endpoint", lambda *_a, **_k: {"ok": True, "models": ["m"], "ctx": {"m": 15000}, "error": None})
    monkeypatch.setattr("gruntly.adapters.qwen.QwenAdapter.detect", lambda self: Detection(True, "x"))
    root = worktree.preflight(repo)
    spec = make_spec("pass", harness="qwen", child_cmd=None, model="m")
    res = runner.execute(root, runner.prepare(build_spec(spec, root), root))
    assert res["status"] == "error" and res["attempts"] == 0 and "15000" in res["error"]
    assert "allow_small_ctx" in res["error"]


def test_small_context_can_be_allowed_explicitly(repo, make_spec, monkeypatch):
    from gruntly import doctor
    from gruntly.adapters.base import Detection
    monkeypatch.setattr(doctor, "probe_endpoint", lambda *_a, **_k: {"ok": True, "models": ["m"], "ctx": {"m": 15000}, "error": None})
    monkeypatch.setattr("gruntly.adapters.qwen.QwenAdapter.detect", lambda self: Detection(True, "x"))
    monkeypatch.setattr("gruntly.adapters.qwen.QwenAdapter.command",
                        lambda self, t, w, p, r: __import__("gruntly.adapters.base", fromlist=["Command"]).Command(
                            [sys.executable, str(__import__("conftest").FAKE), "pass"]))
    root = worktree.preflight(repo)
    spec = make_spec("pass", harness="qwen", child_cmd=None, model="m", allow_small_ctx=True)
    res = runner.execute(root, runner.prepare(build_spec(spec, root), root))
    assert res["status"] == "passed"


def test_queue_busy_reports_who_holds_the_slot(repo):
    root = worktree.preflight(repo)
    held = runner.acquire_slot(root, 1, 600)
    try:
        with pytest.raises(TimeoutError) as e:
            runner.acquire_slot(root, 1, 600, wait_s=1.2)
        assert "queue busy" in str(e.value) and "pid" in str(e.value)
    finally:
        held.unlink()


def test_stats_recommendation_needs_evidence(repo, run_task, make_spec, capsys):
    from gruntly import cli
    run_task(make_spec("pass"))
    cli.main(["stats"])
    s = json.loads(capsys.readouterr().out)
    assert next(iter(s["by_harness_model"].values()))["recommend"].startswith("unknown")


def test_guide_prints_the_manual(capsys):
    from gruntly import cli
    assert cli.main(["guide"]) == 0
    assert "teacher" in capsys.readouterr().out


def test_skill_stays_short():
    from pathlib import Path
    words = len((Path(__file__).parents[2] / "plugin" / "skills" / "gruntly" / "SKILL.md").read_text(encoding="utf8").split())
    assert words < 500, words  # it is loaded into context; the full manual is `gruntly guide` (360 until the 8+ turns rule, --context and a pointer were added, 2026-11-14)


def test_apply_keeps_lf_files_lf_when_autocrlf_is_on(repo, run_task, make_spec):
    from conftest import sh
    sh(repo, "git", "config", "core.autocrlf", "true")
    (repo / "calc.py").write_bytes(b"def add(a, b):\n    return a - b\n")   # LF on disk, as in a repo made on Linux
    res, _ = run_task(make_spec("pass", apply_on_pass=True))
    assert res["status"] == "passed" and res["applied"]
    assert b"\r" not in (repo / "calc.py").read_bytes()


def test_context_file_missing_from_the_snapshot_stops_the_run(repo, run_task, make_spec):
    (repo / ".gitignore").write_text("notes.txt\n")
    (repo / "notes.txt").write_text("the facts\n")
    res, _ = run_task(make_spec("pass", context_files=["notes.txt"]))
    assert res["status"] == "error" and "notes.txt" in res["error"] and "make up" in res["error"]


def test_the_worktree_keeps_lf_files_lf_under_autocrlf(repo, run_task, make_spec):
    from conftest import sh
    sh(repo, "git", "config", "core.autocrlf", "true")
    (repo / "calc.py").write_bytes(b"def add(a, b):\n    return a - b\n")
    seen = {}

    from gruntly import worktree
    real = worktree.create

    def spy(*a, **k):
        w = real(*a, **k)
        seen["bytes"] = (w.path / "calc.py").read_bytes()
        return w

    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(worktree, "create", spy)
    try:
        run_task(make_spec("pass"))
    finally:
        mp.undo()
    assert b"\r" not in seen["bytes"]
