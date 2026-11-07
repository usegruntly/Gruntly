"""CLI-level behaviour: async runs, status, queue, gc, init, stats."""
import json
import time

import yaml

from gruntly import cli, runner, store, worktree


def call(capsys, *argv):
    rc = cli.main(list(argv))
    return rc, capsys.readouterr().out


def test_async_run_status_and_result(repo, make_spec, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    spec = tmp_path / "s.yaml"
    spec.write_text(yaml.safe_dump(make_spec("pass")))
    rc, out = call(capsys, "run", "--spec", str(spec), "--async")
    queued = json.loads(out)
    assert rc == 0 and queued["status"] == "queued"
    rid = queued["run_id"]
    deadline = time.time() + 60
    while time.time() < deadline:
        _, out = call(capsys, "status", rid)
        st = json.loads(out)
        if st["state"] == "done":
            break
        time.sleep(0.5)
    assert st["state"] == "done" and "elapsed_s" in st
    _, out = call(capsys, "result", rid)
    assert json.loads(out)["status"] == "passed"


def test_spec_from_stdin(repo, make_spec, capsys, monkeypatch):
    import io
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.stdin", io.StringIO(yaml.safe_dump(make_spec("pass"))))
    rc, out = call(capsys, "run", "--spec", "-")
    assert rc == 0 and json.loads(out)["status"] == "passed"


def test_bad_spec_is_a_tool_error_not_a_result(repo, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    spec = tmp_path / "bad.yaml"
    spec.write_text("harness: qwen\n")
    assert cli.main(["run", "--spec", str(spec)]) == 2
    assert "brief" in capsys.readouterr().err


def test_not_a_git_repo_fails_clearly(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    s = tmp_path / "s.yaml"
    s.write_text("brief: x\nacceptance: ['true']\n")
    assert cli.main(["run", "--spec", str(s)]) == 2
    assert "not a git repository" in capsys.readouterr().err


def test_failed_gate_is_exit_zero(repo, make_spec, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    s = tmp_path / "s.yaml"
    s.write_text(yaml.safe_dump(make_spec("no_fix", max_attempts=1)))
    rc, out = call(capsys, "run", "--spec", str(s))
    assert rc == 0 and json.loads(out)["status"] == "escalate"


def test_diff_stat_file_and_log(repo, run_task, make_spec, capsys, monkeypatch):
    res, _ = run_task(make_spec("pass"))
    monkeypatch.chdir(repo)
    _, out = call(capsys, "diff", res["run_id"], "--stat")
    assert json.loads(out)["files"][0]["path"] == "calc.py"
    _, out = call(capsys, "diff", res["run_id"], "--file", "calc.py")
    assert "+    return a + b" in out
    _, out = call(capsys, "log", res["run_id"], "--tail", "5")
    assert out.strip()


def test_queue_serialises_runs(repo, tmp_path):
    root = worktree.preflight(repo)
    a = runner.acquire_slot(root, 1, 600)
    try:
        t0 = time.time()
        import threading
        got = []
        t = threading.Thread(target=lambda: got.append(runner.acquire_slot(root, 1, 600, wait_s=10)))
        t.start()
        time.sleep(1.5)
        assert not got  # still waiting for the single slot
        a.unlink()
        t.join(timeout=10)
        assert got and time.time() - t0 < 10
        got[0].unlink()
    finally:
        a.unlink(missing_ok=True)


def test_stale_lock_from_dead_process_is_reclaimed(repo):
    root = worktree.preflight(repo)
    lock = root / ".gruntly" / "locks"
    lock.mkdir(parents=True)
    (lock / "slot0.lock").write_text("999999")
    p = runner.acquire_slot(root, 1, 600, wait_s=5)
    assert p.exists()
    p.unlink()


def test_gc_removes_orphan_worktrees_and_old_runs(repo, run_task, make_spec):
    res, root = run_task(make_spec("pass"))
    rid = res["run_id"]
    # orphan: worktree without a run record
    import shutil
    shutil.rmtree(root / ".gruntly" / "runs" / rid)
    removed = store.gc(root, lambda r: worktree.remove(root, r))
    assert rid in removed and not (root / ".gruntly" / "worktrees" / rid).exists()


def test_init_writes_config_and_snippet(repo, capsys, monkeypatch):
    monkeypatch.chdir(repo)
    rc, out = call(capsys, "init")
    assert rc == 0 and (repo / ".gruntly.toml").exists()
    assert "doctor" in json.loads(out)
    _, out = call(capsys, "init", "--snippet")
    assert "untrusted" in out and "gruntly run --apply-on-pass" in out
    assert ".gruntly/" in (repo / ".git" / "info" / "exclude").read_text()


def test_stats_aggregates_runs(repo, run_task, make_spec, capsys):
    run_task(make_spec("pass"))
    run_task(make_spec("no_fix", max_attempts=1))
    _, out = call(capsys, "stats")
    s = json.loads(out)
    b = s["by_harness_model"]["generic/None/ctx=?/default"]
    assert s["total_runs"] == 2 and b["passed"] == 1 and b["escalated"] == 1 and b["pass_rate"] == 0.5


def test_user_status_is_clean_during_and_after_runs(repo, run_task, make_spec):
    run_task(make_spec("pass"))
    status = worktree.git(["status", "--porcelain"], repo).stdout
    assert status.strip() == ""  # .gruntly/ never shows up


def test_doctor_reports_checks(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "c"))
    rc, out = call(capsys, "doctor")
    names = {c["check"] for c in json.loads(out)["checks"]}
    assert rc == 0 and {"git", "model_server", "sandbox", "child:qwen"} <= names


def test_continue_via_cli(repo, make_spec, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    s = tmp_path / "s.yaml"
    s.write_text(yaml.safe_dump(make_spec("handoff", max_attempts=1)))
    _, out = call(capsys, "run", "--spec", str(s))
    res = json.loads(out)
    assert res["failure_bundle"]["context_exhausted"]
    assert any("continue" in n for n in res["next"])
    _, out = call(capsys, "continue", res["run_id"], "--guidance", "change the operator", "--attempts", "1")
    assert json.loads(out)["status"] == "passed"
