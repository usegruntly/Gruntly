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


def test_a_follow_up_reuses_the_run(proj, capsys, monkeypatch):
    first = say(capsys, monkeypatch, proj, "fix add() so test_calc passes")
    rid = next(ln.split(": ", 1)[1] for ln in first.splitlines() if ln.startswith("run: "))
    second = say(capsys, monkeypatch, proj, "also keep the names", "--continue", rid)
    assert second.startswith(agent.OPEN) and f"run: {rid}" in second


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
