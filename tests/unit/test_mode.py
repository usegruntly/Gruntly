import io
import sys

import pytest

from gruntly import agent, cli, mode, worktree


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("GRUNTLY_MODE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)


def test_default_is_auto_and_the_project_file_changes_it(repo):
    root = worktree.preflight(repo)
    assert mode.resolve(root) == ("auto", "default")
    mode.set_mode(root, "off")
    assert mode.resolve(root) == ("off", "project")
    assert (repo / ".gruntly" / "mode").read_text().strip() == "off"


def test_a_session_beats_the_project_and_other_sessions_are_unaffected(repo, monkeypatch):
    root = worktree.preflight(repo)
    mode.set_mode(root, "off")                                   # project: off
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-a")
    mode.set_mode(root, "on", "session")                         # this chat: on
    assert mode.resolve(root) == ("on", "session")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-b")       # another chat in the same project
    assert mode.resolve(root) == ("off", "project")
    monkeypatch.setenv("GRUNTLY_MODE", "auto")                   # the environment beats both
    assert mode.resolve(root) == ("auto", "environment")


def test_a_session_mode_needs_a_session(repo):
    with pytest.raises(ValueError, match="no session id"):
        mode.set_mode(worktree.preflight(repo), "on", "session")


def test_old_session_files_are_pruned(repo, monkeypatch):
    import os
    import time
    root = worktree.preflight(repo)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "new")
    old = repo / ".gruntly" / "sessions" / "ancient.mode"
    old.parent.mkdir(parents=True)
    old.write_text("on\n")
    os.utime(old, (time.time() - 40 * 86400,) * 2)
    mode.set_mode(root, "on", "session")
    assert not old.exists() and (repo / ".gruntly" / "sessions" / "new.mode").exists()


def say(capsys, monkeypatch, repo, *argv, text=""):
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    assert cli.main(list(argv)) == 0
    return capsys.readouterr().out.strip()


def test_agent_run_while_off_refuses_in_one_line_and_runs_nothing(repo, capsys, monkeypatch):
    from tests.e2e.test_do import write_config
    write_config(repo)
    mode.set_mode(worktree.preflight(repo), "off")
    out = say(capsys, monkeypatch, repo, "agent-run", text="fix add() so test_calc passes")
    assert out.startswith(agent.OPEN) and "status: refused" in out and "switched OFF for this project" in out
    assert "do this change yourself" in out
    assert not (repo / ".gruntly" / "runs").exists() or not list((repo / ".gruntly" / "runs").iterdir())
    assert "a - b" in (repo / "calc.py").read_text()          # untouched


def test_the_guard_covers_ask_continue_do_and_run(repo, capsys, monkeypatch):
    from tests.e2e.test_do import write_config
    write_config(repo)
    mode.set_mode(worktree.preflight(repo), "off")
    assert "switched OFF" in say(capsys, monkeypatch, repo, "agent-run", "--ask", text="who maintains this?")
    assert "switched OFF" in say(capsys, monkeypatch, repo, "agent-run", "--continue", "r_nope", text="more")
    assert "switched OFF" in say(capsys, monkeypatch, repo, "do", text="fix add()")
    out = say(capsys, monkeypatch, repo, "run", "--spec", "-", text="brief: x\nacceptance: ['true']\n")
    assert '"status": "refused"' in out and "switched OFF" in out


def test_on_and_auto_do_not_block_and_wait_still_works_while_off(repo, capsys, monkeypatch):
    from tests.e2e.test_do import write_config
    write_config(repo)
    root = worktree.preflight(repo)
    mode.set_mode(root, "on")
    out = say(capsys, monkeypatch, repo, "agent-run", text="fix add() so test_calc passes")
    assert "status: passed" in out
    mode.set_mode(root, "off")
    assert cli.main(["mode"]) == 0
    assert "gruntly mode: off (from project)" in capsys.readouterr().out
    assert mode.refusal(root) is not None and mode.refusal(worktree.preflight(repo)) is not None


def test_the_mode_command_sets_shows_and_rejects(repo, capsys, monkeypatch):
    monkeypatch.chdir(repo)
    assert cli.main(["mode", "on"]) == 0
    assert "mode set to on for this project" in capsys.readouterr().out
    assert cli.main(["mode", "--session", "off"]) == 2           # no session id outside Claude Code
    assert "no session id" in capsys.readouterr().err
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")
    assert cli.main(["mode", "--session", "off"]) == 0
    out = capsys.readouterr().out
    assert "for this session" in out and "note" not in out
    assert cli.main(["mode"]) == 0 and "off (from session)" in capsys.readouterr().out
