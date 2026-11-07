"""End-to-end runs against the scripted fake child. Offline, GPU-free."""
import json

from gruntly import runner, store, worktree
from gruntly.result import MAX_CHARS

SECRET = "sk-test1234567890abcdefghijklmnop"


def test_pass(run_task, make_spec):
    res, root = run_task(make_spec("pass"))
    assert res["status"] == "passed"
    assert res["attempts"] == 1
    assert all(v is True for v in res["gates"].values())
    assert res["diff_stat"]["paths"] == ["calc.py"]
    assert "untrusted" not in res and "child_summary" not in res  # nothing child-written on a pass
    assert len(json.dumps(res)) <= 600  # a pass is tiny
    # user's tree is untouched until apply
    assert "a - b" in (root / "calc.py").read_text()


def test_fails_gate_then_escalates(run_task, make_spec):
    res, _ = run_task(make_spec("no_fix", max_attempts=3))
    assert res["status"] == "escalate"
    assert res["gates"]["acceptance"]["ok"] is False
    assert "assert" in res["untrusted"]["gate_output"]
    assert res["failure_bundle"]["gate"] == "acceptance"
    assert "stuck" in res["failure_bundle"]["reason"]  # identical failure twice stops early
    assert res["attempts"] == 2


def test_retry_recovers(run_task, make_spec):
    res, _ = run_task(make_spec("fix_on_retry", max_attempts=3))
    assert res["status"] == "passed", res
    assert res["attempts"] == 2


def test_edit_outside_scope(run_task, make_spec):
    res, _ = run_task(make_spec("out_of_scope", max_attempts=1))
    assert res["status"] == "escalate"
    assert res["gates"]["scope"]["ok"] is False
    assert "other.py" in res["gates"]["scope"]["violations"][0]


def test_absolute_path_write_to_main_tree(run_task, make_spec):
    res, root = run_task(make_spec("main_tree", max_attempts=1, allowed_paths=["calc.py", "**"]))
    assert res["status"] == "escalate"
    assert any("main tree modified: leaked.txt" in v for v in res["gates"]["scope"]["violations"])


def test_hang_hits_no_progress_timeout(run_task, make_spec):
    res, _ = run_task(make_spec("hang", no_progress_s=2, max_attempts=3))
    assert res["status"] == "timeout"
    assert "no progress" in res["failure_bundle"]["reason"]
    assert res["attempts"] == 1


def test_wall_budget(run_task, make_spec):
    res, _ = run_task(make_spec("hang_noisy", budget_s=6, no_progress_s=60))
    assert res["status"] == "timeout"
    assert "budget" in res["failure_bundle"]["reason"]


def test_test_weakening(run_task, make_spec):
    res, _ = run_task(make_spec("weaken", max_attempts=1, allowed_paths=["calc.py", "test_calc.py"]))
    assert res["gates"]["acceptance"] is True  # the tests "pass"...
    assert res["status"] == "escalate"                # ...but the gate wins
    assert not res["gates"]["test_weakening"]["ok"]


def test_deleted_tests(run_task, make_spec):
    res, _ = run_task(make_spec("delete_tests", max_attempts=1, allowed_paths=["**"]))
    assert res["status"] == "escalate"
    assert any("deleted test file" in f for f in res["gates"]["test_weakening"]["findings"])


def test_tests_writable_allows_edits(run_task, make_spec):
    res, _ = run_task(make_spec("weaken", max_attempts=1, tests_writable=True, allowed_paths=["calc.py", "test_calc.py"]))
    assert res["status"] == "passed"


def test_secret_is_redacted_everywhere(run_task, make_spec):
    res, root = run_task(make_spec("secret"))
    assert res["status"] == "passed"
    assert SECRET not in json.dumps(res)
    for p in (root / ".gruntly" / "runs").rglob("*"):
        if p.is_file():
            assert SECRET not in p.read_text(encoding="utf8", errors="replace"), p


def test_malformed_tool_calls_escalate_early(run_task, make_spec):
    res, _ = run_task(make_spec("malformed", max_attempts=3))
    assert res["status"] == "escalate"
    assert "malformed" in res["failure_bundle"]["reason"]
    assert res["attempts"] == 1


def test_new_deps_gate(run_task, make_spec):
    res, _ = run_task(make_spec("deps", max_attempts=1, allowed_paths=["**"]))
    assert res["status"] == "escalate"
    assert not res["gates"]["new_deps"]["ok"]


def test_diff_size_gate(run_task, make_spec):
    res, _ = run_task(make_spec("big", max_attempts=1))
    assert not res["gates"]["diff_size"]["ok"]
    assert res["status"] == "escalate"


def test_infra_error_spends_no_attempt(run_task, make_spec):
    res, _ = run_task(make_spec("server_down"))
    assert res["status"] == "error"
    assert "model server" in res["error"]


def test_unreachable_model_server_is_error_before_any_attempt(run_task, make_spec):
    res, _ = run_task(make_spec("pass", harness="qwen", child_cmd=None, endpoint="http://127.0.0.1:9/v1"))
    assert res["status"] == "error"
    assert res["attempts"] == 0


def test_handoff_relay_across_runs(run_task, make_spec):
    """Child 1 runs out of context and leaves notes; the parent continues with guidance."""
    res, root = run_task(make_spec("handoff", max_attempts=1))
    assert res["status"] == "escalate"
    assert res["failure_bundle"]["context_exhausted"] is True
    assert "calc.py" in res["untrusted"]["handoff"]
    res2 = runner.execute(root, res["run_id"], guidance="Just change the operator.", extra_attempts=1)
    assert res2["status"] == "passed"
    assert res2["attempts"] == 2  # attempt counter carries on across the relay


def test_apply_then_discard(repo, run_task, make_spec, capsys, monkeypatch):
    from gruntly import cli
    res, root = run_task(make_spec("pass"))
    rid = res["run_id"]
    monkeypatch.chdir(repo)
    assert cli.main(["apply", rid]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["applied"] is True and applied["committed"] is False
    assert "a + b" in (repo / "calc.py").read_text()
    assert cli.main(["discard", rid]) == 0
    assert not (repo / ".gruntly" / "worktrees" / rid).exists()


def test_apply_refuses_when_scope_violated(repo, run_task, make_spec, capsys, monkeypatch):
    from gruntly import cli
    res, _ = run_task(make_spec("out_of_scope", max_attempts=1))
    monkeypatch.chdir(repo)
    cli.main(["apply", res["run_id"]])
    out = json.loads(capsys.readouterr().out)
    assert out["applied"] is False and "scope" in out["error"]
    assert "a - b" in (repo / "calc.py").read_text()


def test_apply_allows_parent_edits_made_after_the_run(repo, run_task, make_spec, capsys, monkeypatch):
    from gruntly import cli
    res, _ = run_task(make_spec("pass"))
    (repo / "notes.txt").write_text("parent kept working\n")
    monkeypatch.chdir(repo)
    cli.main(["apply", res["run_id"]])
    assert json.loads(capsys.readouterr().out)["applied"] is True
