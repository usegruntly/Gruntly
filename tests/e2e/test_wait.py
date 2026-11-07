"""Foreground waiting: gruntly never ends the parent's turn, so the conversation is not replayed in a second session."""
import json
import time
from pathlib import Path

import yaml

from gruntly import cli, runner, store, worktree


def call(capsys, *argv):
    rc = cli.main(list(argv))
    return rc, json.loads(capsys.readouterr().out)


def write_spec(tmp_path, make_spec, scenario, **over):
    p = tmp_path / "s.yaml"
    p.write_text(yaml.safe_dump(make_spec(scenario, **over)))
    return str(p)


def test_run_blocks_and_returns_the_result_in_one_call(repo, make_spec, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    rc, res = call(capsys, "run", "--spec", write_spec(tmp_path, make_spec, "pass"), "--apply-on-pass")
    assert rc == 0 and res["status"] == "passed" and res["applied"] is True
    assert "a + b" in (repo / "calc.py").read_text()


def test_a_slow_run_returns_running_then_wait_returns_the_result(repo, make_spec, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    t0 = time.time()
    _, running = call(capsys, "run", "--spec", write_spec(tmp_path, make_spec, "slow_pass"), "--max-block", "1")
    assert running["status"] == "running" and time.time() - t0 < 4
    assert running["next"] == [f"gruntly wait {running['run_id']}"]
    assert len(json.dumps(running)) < 300  # the parent pays for almost nothing while it waits
    _, res = call(capsys, "wait", running["run_id"], "--timeout", "60")
    assert res["status"] == "passed"


def test_wait_times_out_with_a_tiny_status_and_the_run_survives(repo, make_spec, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    _, running = call(capsys, "run", "--spec", write_spec(tmp_path, make_spec, "slow_pass"), "--max-block", "1")
    _, still = call(capsys, "wait", running["run_id"], "--timeout", "1")
    assert still["status"] in ("running", "passed")  # either way nothing was lost
    _, res = call(capsys, "wait", running["run_id"], "--timeout", "60")
    assert res["status"] == "passed"


def test_wait_reports_a_worker_that_died_without_a_result(repo, make_spec, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    root = worktree.preflight(repo)
    from gruntly.spec import build_spec
    rid = runner.prepare(build_spec(make_spec("pass"), root), root)
    store.Store(root, rid).set_state("running", pid=999999)  # no such process
    time.sleep(3.2)
    _, res = call(capsys, "wait", rid, "--timeout", "5")
    assert res["status"] == "error" and "ended without a result" in res["error"]


def test_continue_blocks_and_does_not_return_the_previous_result(repo, make_spec, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    _, first = call(capsys, "run", "--spec", write_spec(tmp_path, make_spec, "handoff", max_attempts=1))
    assert first["status"] == "escalate"
    _, second = call(capsys, "continue", first["run_id"], "--guidance", "change the operator", "--attempts", "1")
    assert second["status"] == "passed" and second["attempts"] == 2


def test_in_process_mode_still_available(repo, make_spec, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    _, res = call(capsys, "run", "--spec", write_spec(tmp_path, make_spec, "pass"), "--max-block", "0")
    assert res["status"] == "passed"


def test_skill_and_guide_forbid_backgrounding():
    from pathlib import Path
    root = Path(__file__).parents[2]
    skill = (root / "plugin" / "skills" / "gruntly" / "SKILL.md").read_text(encoding="utf8")
    assert "Never use `run_in_background`" in skill and "gruntly wait" in skill and "300000" in skill
    guide = (root / "src" / "gruntly" / "GUIDE.md").read_text(encoding="utf8")
    assert "run_in_background" in guide and "gruntly wait" in guide
    assert "run_in_background" not in cli.SNIPPET.replace("never run_in_background", "")


def test_bench_counts_session_splits_and_background_calls():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_bench", Path(__file__).parents[2] / "bench" / "run_bench.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    lines = [
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"usage": {}, "content": [{"type": "tool_use", "name": "Bash", "input": {"run_in_background": True}}]}},
        {"type": "system", "subtype": "init"},
        {"type": "result", "total_cost_usd": 0.1, "num_turns": 2, "usage": {}},
    ]
    out = m.analyse("\n".join(json.dumps(x) for x in lines))
    assert out["sessions"] == 2 and out["background_calls"] == 1
