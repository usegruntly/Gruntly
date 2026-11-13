"""Parent adapters: the two prompt categories, Claude Code behind the interface with the command line pinned, and the runner."""
import json
import sys

import pytest

from gruntly import agent, parents
from gruntly.adapters.base import Detection
from gruntly.parents import base, claude, prompts


@pytest.fixture
def exe(monkeypatch):
    monkeypatch.setattr(claude, "which", lambda name: "/bin/claude")
    return "/bin/claude"


def test_there_are_two_prompt_categories_and_the_old_name_is_the_delegating_one():
    assert agent.LEAN_PROMPT is prompts.DELEGATING
    assert "gruntly agent-run" in prompts.DELEGATING and prompts.OPEN in prompts.DELEGATING and "GRUNTLY-FALLBACK" in prompts.DELEGATING
    assert "Do the task yourself" in prompts.WORKING and "gruntly" not in prompts.WORKING
    for text in (prompts.DELEGATING, prompts.WORKING):                       # they travel on a command line or in a file: plain text only
        assert '"' not in text and "<" not in text and ">" not in text


def test_a_working_task_is_the_task_plus_one_instruction_and_an_escalation_says_what_was_tried():
    assert prompts.working_task("Fix add().\n") == "Fix add().\n\n" + prompts.WORKING
    text = prompts.working_task("Fix add().", "GRUNTLY-FALLBACK: stuck (run r_1)")
    assert text.startswith("Fix add().") and "could not finish it (stuck (run r_1))" in text and "GRUNTLY-FALLBACK" not in text
    assert text == agent.escalation_task("Fix add().", "GRUNTLY-FALLBACK: stuck (run r_1)")
    assert "(" not in prompts.working_task("x", "").split("finish it", 1)[1].split(".", 1)[0]                  # no empty reason in brackets


def test_the_delegating_command_line_is_exactly_the_one_the_benchmarks_measured(exe):
    cmd = claude.ClaudeParent().command("Fix add().", "delegating", "sonnet")
    assert cmd.argv == [exe, "-p", "--model", "sonnet", "--output-format", "text", "--system-prompt", prompts.DELEGATING, "--tools", "Bash",
                        "--allowedTools", "Bash(gruntly *)", "--strict-mcp-config", "--disable-slash-commands"]
    assert cmd.stdin == "Fix add()." and cmd.env == {"BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "600000"} and cmd.notes == []
    assert agent.lean_command("Fix add().", "sonnet")[0] == cmd.argv                       # the old entry point gives the same line


def test_a_working_session_is_claude_code_as_shipped_with_the_edit_tools_allowed(exe):
    cmd = claude.ClaudeParent().command("Fix add().", "working", "sonnet")
    assert cmd.argv == [exe, "-p", "--model", "sonnet", "--output-format", "text", "--allowedTools", claude.FULL_TOOLS]
    for flag in ("--system-prompt", "--tools", "--strict-mcp-config", "--disable-slash-commands"):
        assert flag not in cmd.argv
    assert agent.lean_command("Fix add().", "sonnet", full=True)[0] == cmd.argv


def test_structured_output_default_model_and_an_ignored_provider_are_said_out_loud(exe):
    cmd = claude.ClaudeParent().command("t", "delegating", None, "openrouter", structured=True)
    assert cmd.argv[:7] == [exe, "-p", "--model", "sonnet", "--output-format", "stream-json", "--verbose"]
    assert cmd.notes and "Anthropic only" in cmd.notes[0] and "openrouter" in cmd.notes[0]
    assert claude.ClaudeParent().command("t", "delegating", None, "anthropic").notes == []
    with pytest.raises(ValueError, match="mode must be one of delegating, working"):
        claude.ClaudeParent().command("t", "lean")


def test_text_output_is_the_reply_and_stream_json_gives_usage_cost_and_turns():
    p = claude.ClaudeParent()
    assert p.parse("  done.\n", "", 0).final_message == "done." and p.parse("boom", "", 1).is_error
    res = {"type": "result", "subtype": "success", "result": "All fixed.", "session_id": "s1", "num_turns": 2, "total_cost_usd": 0.0456,
           "usage": {"input_tokens": 4, "output_tokens": 369, "cache_read_input_tokens": 25435, "cache_creation_input_tokens": 26272}}
    out = p.parse('{"type":"system"}\n' + json.dumps(res) + "\n", "", 0)
    assert (out.final_message, out.session_id, out.turns, out.cost_usd, out.is_error) == ("All fixed.", "s1", 2, 0.0456, False)
    assert out.usage.prompt == 4 + 25435 + 26272 and out.usage.completion == 369 and out.usage.cached == 25435
    assert p.parse(json.dumps({**res, "subtype": "error_max_turns", "result": ""}), "", 0).is_error


def test_claude_reports_what_it_can_do_of_the_lean_setup():
    c = claude.ClaudeParent().capabilities()
    assert (c.replace_system_prompt, c.restrict_tools, c.restrict_shell, c.disable_extensions, c.reports_usage, c.reports_cost, c.experimental) == \
        (True, True, True, True, True, True, False)


def test_the_registry_knows_claude_and_names_what_is_known_when_asked_for_another(monkeypatch):
    assert "claude" in parents.names() and isinstance(parents.get_parent("claude"), claude.ClaudeParent)
    with pytest.raises(ValueError, match="unknown parent harness 'nope'; known: claude"):
        parents.get_parent("nope")
    monkeypatch.setattr(parents, "table", lambda: {"claude": claude.ClaudeParent})              # isolate from the other registered harnesses
    monkeypatch.setattr(claude.ClaudeParent, "detect", lambda self: Detection(False))
    assert parents.pick_installed() is None
    monkeypatch.setattr(claude.ClaudeParent, "detect", lambda self: Detection(True, "x"))
    assert parents.pick_installed() == "claude"


class ScriptParent:
    """A parent adapter whose 'harness' is a python one-liner: echoes its stdin and one environment variable."""
    name = "script"

    def __init__(self, code):
        self.code = code

    def detect(self):
        return Detection(True)

    def command(self, task, mode, model=None, provider=None, structured=False):
        return base.ParentCommand([sys.executable, "-c", self.code], {"PARENT_MARK": f"{mode}:{model}"}, task, {"conf/parent.txt": "settings"}, ["a limit"])

    def parse(self, stdout, stderr, exit_code):
        return base.ParentOutcome(stdout.strip(), exit_code != 0)

    def capabilities(self):
        return base.ParentCaps()

    def cancel(self, proc):
        pass


def test_the_runner_writes_files_gives_the_task_on_stdin_merges_the_environment_and_parses(tmp_path):
    r = base.run(ScriptParent("import os, sys; print(sys.stdin.read() + '|' + os.environ['PARENT_MARK'] + '|' + os.environ['EXTRA'])"),
                 "the task", "delegating", "m1", cwd=tmp_path, env={"EXTRA": "e"})
    assert r.outcome.final_message == "the task|delegating:m1|e" and r.returncode == 0 and not r.outcome.is_error
    assert (tmp_path / "conf" / "parent.txt").read_text() == "settings" and r.command.notes == ["a limit"]


def test_a_missing_harness_and_a_timeout_are_error_outcomes_not_exceptions(tmp_path, monkeypatch):
    class Missing(ScriptParent):
        def command(self, *a, **k):
            return base.ParentCommand(["definitely-not-a-real-harness-xyz"], {}, "t")
    r = base.run(Missing(""), "t", "working", cwd=tmp_path)
    assert r.returncode == 127 and r.outcome.is_error and "not installed" in r.outcome.final_message
    slow = base.run(ScriptParent("import time; time.sleep(5)"), "t", "working", cwd=tmp_path, timeout_s=1)
    assert slow.returncode == 124 and slow.outcome.is_error and "did not finish in 1 s" in slow.outcome.final_message


def test_run_agent_names_the_missing_harness_and_returns_127(monkeypatch, capsys):
    def boom(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(base.subprocess, "run", boom)
    assert agent.run_agent("Fix it.") == 127
    assert "not installed or not on PATH" in capsys.readouterr().err
