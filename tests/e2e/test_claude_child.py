"""Claude Code as the child, end to end through the runner with a stand-in `claude` on PATH. Offline, no model, no money."""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from gruntly.agent import cost_line

FAKE = Path(__file__).parents[1] / "fake_child" / "fake_claude.py"


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """Put a `claude` on PATH that runs the scripted stand-in with the chosen scenario."""
    bindir = tmp_path / "bin"
    bindir.mkdir()

    def use(name):
        if os.name == "nt":
            (bindir / "claude.cmd").write_text(f'@echo off\r\n"{sys.executable}" "{FAKE}" {name} %*\r\n')
        else:
            sh = bindir / "claude"
            sh.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" {name} "$@"\n')
            sh.chmod(sh.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    use("pass")
    return use


def spec(make_spec, **over):
    d = make_spec("unused", harness="claude", model="haiku", **over)
    d.pop("child_cmd", None)
    return d


def calls(root):
    files = list((root / ".git" / "worktrees").glob("*/fake_claude_call.json"))
    return json.loads(files[0].read_text()) if files else []


def test_a_claude_child_passes_without_any_model_server_and_its_dollars_are_counted(run_task, make_spec, fake_claude):
    res, root = run_task(spec(make_spec))                   # no LM Studio here: the endpoint probe must not run for this harness
    assert res["status"] == "passed", res
    assert res["child"]["harness"] == "claude" and res["child"]["model"] == "haiku"
    assert res["child"]["cost_usd"] == 0.01 and res["child"]["requests"] == 5 and res["child"]["tokens"] == 8930
    assert "your Claude usage" in cost_line(res["child"])
    sent = calls(root)[0]
    assert "TASK:\nFix add() in calc.py." in sent["prompt"] and "Edit only files matching: calc.py" in sent["prompt"]
    assert sent["flags"][sent["flags"].index("--model") + 1] == "haiku"


def test_a_failed_first_attempt_is_resumed_with_the_failure_and_both_attempts_are_paid(run_task, make_spec, fake_claude):
    fake_claude("fix_on_retry")
    res, root = run_task(spec(make_spec, max_attempts=3))
    assert res["status"] == "passed" and res["attempts"] == 2
    first, second = calls(root)
    assert "--resume" not in first["flags"]
    assert second["flags"][second["flags"].index("--resume") + 1] == "sess-1"        # the same session carries on
    assert "did not pass the 'acceptance' check" in second["prompt"]                  # and is told what failed, once
    assert res["child"]["cost_usd"] == pytest.approx(0.012)                           # 0.005 + 0.007: every attempt counts


def test_running_out_of_budget_is_reported_as_a_failure_not_a_pass(run_task, make_spec, fake_claude):
    fake_claude("out_of_budget")
    res, _ = run_task(spec(make_spec, max_attempts=1))
    assert res["status"] != "passed"


def test_a_missing_claude_is_a_clear_error(run_task, make_spec, monkeypatch):
    monkeypatch.setattr("gruntly.adapters.claude.which", lambda name: None)           # claude is not installed
    res, _ = run_task(spec(make_spec))
    assert res["status"] == "error" and "claude" in res["error"].lower()
