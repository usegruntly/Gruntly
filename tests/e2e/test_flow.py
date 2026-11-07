"""The optimized parent flow: one-call apply, holdout, red-before-green, context preflight, injection boundary."""
import json
import subprocess
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


HOLDOUT = "from calc import add\n\ndef test_holdout_negative():\n    assert add(-2, -3) == -5\n    assert add(0, 0) == 0\n"


def test_holdout_files_never_reach_the_child_and_never_enter_the_diff(repo, make_spec):
    (repo / "holdout_calc.py").write_text(HOLDOUT)
    root = worktree.preflight(repo)
    spec = make_spec("pass", holdout={"files": ["holdout_calc.py"], "cmd": f'"{sys.executable}" -m pytest -q holdout_calc.py'},
                     allowed_paths=["calc.py"])
    rid = runner.prepare(build_spec(spec, root), root)
    res = runner.execute(root, rid)
    assert res["status"] == "passed", res
    assert res["diff_stat"]["paths"] == ["calc.py"]
    wt = root / ".gruntly" / "worktrees" / rid
    assert not (wt / "holdout_calc.py").exists()


def test_holdout_catches_what_the_visible_test_misses(repo, make_spec):
    """A child that special-cases the visible test passes acceptance but fails the held-out edge cases."""
    (repo / "holdout_calc.py").write_text(HOLDOUT)
    root = worktree.preflight(repo)
    spec = make_spec("hardcode", holdout={"files": ["holdout_calc.py"], "cmd": f'"{sys.executable}" -m pytest -q holdout_calc.py'},
                     allowed_paths=["calc.py"], max_attempts=1)
    res = runner.execute(root, runner.prepare(build_spec(spec, root), root))
    assert res["gates"]["acceptance"] is True
    assert res["gates"]["holdout"]["ok"] is False and res["status"] == "escalate"
    # the child may be told which holdout tests failed, but never their bodies or assertion text
    assert "assert add(-2" not in json.dumps(res)


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
    spec = make_spec("pass", harness="qwen", child_cmd=None, model="m", profile="default")
    res = runner.execute(root, runner.prepare(build_spec(spec, root), root))
    assert res["status"] == "error" and res["attempts"] == 0 and "15000" in res["error"]
    assert "allow_small_ctx" in res["error"]


def test_small_context_can_be_allowed_explicitly(repo, make_spec, monkeypatch):
    from gruntly import doctor
    from gruntly.adapters.base import Detection
    monkeypatch.setattr(doctor, "probe_endpoint", lambda *_a, **_k: {"ok": True, "models": ["m"], "ctx": {"m": 15000}, "error": None})
    monkeypatch.setattr("gruntly.adapters.qwen.QwenAdapter.detect", lambda self: Detection(True, "x"))
    monkeypatch.setattr("gruntly.adapters.qwen.QwenAdapter.command",
                        lambda self, t, w, p, r, profile=None: __import__("gruntly.adapters.base", fromlist=["Command"]).Command(
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
    assert "holdout" in capsys.readouterr().out


def test_skill_stays_short():
    from pathlib import Path
    words = len((Path(__file__).parents[2] / "plugin" / "skills" / "gruntly" / "SKILL.md").read_text(encoding="utf8").split())
    assert words < 330, words  # it is loaded into context; the full manual is `gruntly guide`


def test_holdout_outside_the_repo_fails_fast_with_a_clear_message(repo, make_spec, tmp_path):
    """Found in the benchmark: a parent put its holdout test in a temp dir and got a raw git error after wasting a turn."""
    from gruntly.spec import SpecError
    outside = tmp_path / "elsewhere" / "holdout_calc.py"
    outside.parent.mkdir()
    outside.write_text(HOLDOUT)
    root = worktree.preflight(repo)
    spec = make_spec("pass", holdout={"files": [str(outside)], "cmd": "pytest -q"})
    with pytest.raises(SpecError) as e:
        build_spec(spec, root)
    assert "outside the repo" in str(e.value) and "untracked is fine" in str(e.value)


def test_missing_holdout_file_fails_before_the_child_runs(repo, make_spec):
    from gruntly.spec import SpecError
    root = worktree.preflight(repo)
    with pytest.raises(SpecError, match="does not exist"):
        build_spec(make_spec("pass", holdout={"files": ["nope.py"], "cmd": "pytest -q"}), root)
