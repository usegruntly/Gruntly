"""`gruntly agent-run`: one marked result block, and a follow-up that keeps the same run."""
import io
import sys

import pytest

from gruntly import agent, cli
from tests.e2e.test_do import write_config  # noqa: F401  (same fake child setup)


def say(capsys, monkeypatch, repo, request, *flags):
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.stdin", io.StringIO(request))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    assert cli.main(["agent-run", *flags]) == 0
    return capsys.readouterr().out.strip()


@pytest.fixture
def proj(repo):
    write_config(repo)
    return repo


def test_the_result_is_one_marked_block_with_status_files_and_diff(proj, capsys, monkeypatch):
    out = say(capsys, monkeypatch, proj, "fix add() so test_calc passes")
    assert out.startswith(agent.OPEN) and out.endswith(agent.CLOSE), out
    assert "status: passed" in out and "calc.py" in out and "a + b" in out
    assert "[untrusted diff" in out and "full patch: .gruntly/runs/" in out
    assert out.count(agent.OPEN) == 1


def test_the_contract_of_changed_functions_is_included(proj, capsys, monkeypatch):
    out = say(capsys, monkeypatch, proj, "fix add() so test_calc passes")
    assert "def add(" in out.split("contract", 1)[1]


def test_a_refusal_is_a_block_too(proj, capsys, monkeypatch):
    out = say(capsys, monkeypatch, proj, "rewrite the flux capacitor")
    assert out.startswith(agent.OPEN) and "status: refused" in out


def test_a_long_diff_is_truncated_and_flagged():
    patch = "\n".join(f"+line {i}" for i in range(300))
    out = agent.block({"run_id": "r1", "status": "passed", "applied": True, "diff_stat": {"paths": ["a.py"]}}, None, patch=patch)
    assert "diff truncated" in out and "more lines" in out


def test_child_text_stays_inside_fences():
    out = agent.block({"run_id": "r1", "status": "failed", "untrusted": {"gate_output": "IGNORE ALL"}}, None)
    assert out.index("[untrusted") < out.index("IGNORE ALL") < out.index("[end untrusted]")


def test_the_lean_command_has_one_tool_and_no_plugins():
    argv, _ = agent.lean_command("t", "sonnet")
    assert argv[argv.index("--tools") + 1] == "Bash" and "--strict-mcp-config" in argv and "--disable-slash-commands" in argv
    full, _ = agent.lean_command("t", "sonnet", full=True)
    assert "--tools" not in full and "--system-prompt" not in full


def test_a_follow_up_after_an_applied_run_starts_a_new_run_on_the_current_tree(proj, capsys, monkeypatch):
    first = say(capsys, monkeypatch, proj, "fix add() so test_calc passes")
    assert "status: passed" in first
    rid = next(ln.split(": ", 1)[1] for ln in first.splitlines() if ln.startswith("run: "))
    assert not (proj / ".gruntly" / "worktrees" / rid).exists()  # applied runs drop their worktree
    second = say(capsys, monkeypatch, proj, "also keep the names", "--continue", rid)
    assert second.startswith(agent.OPEN) and "worktree is gone" not in second, second


def test_the_trace_line_and_trace_flags_reach_the_block():
    r = {"run_id": "r1", "status": "passed", "applied": True, "diff_stat": {"paths": ["a.py"]},
         "child_trace": "child: 3 tool calls (read x1, edit x1, run x1), 0 failed, 1 test run",
         "review_hint": ["the child repeated one tool call 3 times"]}
    out = agent.block(r, None, patch="+x")
    assert "child: 3 tool calls" in out and "repeated one tool call 3 times" in out


def test_a_flag_is_not_listed_twice():
    r = {"run_id": "r1", "status": "passed", "applied": True, "diff_stat": {"paths": ["a.py"]},
         "review_hint": ["weak acceptance: tests pass first"], "warnings": ["tests pass first"]}
    assert agent.block(r, None).count("tests pass first") == 1


def commit(repo, *names):
    import subprocess
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "more"], cwd=repo, check=True)


def test_a_request_naming_two_files_is_split_per_file(proj):
    (proj / "other.py").write_text("def sub(a, b):\n    return a + b\n")
    commit(proj)
    parts = agent.split_request("Fix the bugs in calc.py and other.py", proj)
    assert len(parts) == 2 and parts[0].startswith("In calc.py") and "other.py" not in parts[0]
    assert agent.split_request("fix add() in calc.py", proj) == ["fix add() in calc.py"]


def test_two_part_blocks_are_joined_into_one_block():
    one = agent.block(None, None, error="a")
    two = agent.join_blocks([one, agent.block(None, None, error="b")])
    assert two.count(agent.OPEN) == 1 and two.count(agent.CLOSE) == 1 and "part 2 of 2" in two


def test_no_covering_test_runs_against_the_whole_suite_with_a_flag(proj, capsys, monkeypatch):
    (proj / "util.py").write_text("def noop():\n    return 1\n")
    commit(proj)
    out = say(capsys, monkeypatch, proj, "change noop() in util.py to return 2")
    assert out.startswith(agent.OPEN) and "no test covered this code" in out
    assert "status: refused" not in out


def test_other_refusals_are_not_loosened(proj, capsys, monkeypatch):
    out = say(capsys, monkeypatch, proj, "rewrite the flux capacitor")
    assert "status: refused" in out
