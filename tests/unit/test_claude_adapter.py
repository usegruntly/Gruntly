import json

from gruntly import harnesses
from gruntly.adapters.base import INSTALL_ORDER, get_adapter
from gruntly.adapters.claude import ClaudeAdapter
from gruntly.agent import cost_line
from gruntly.spec import build_spec


def task(**over):
    return build_spec({"brief": "x", "acceptance": ["true"], "harness": "claude", "model": "haiku", **over})


def result_line(**over):
    base = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 7, "result": "Done.\nChanged utils.py.",
            "session_id": "abc-123", "total_cost_usd": 0.0123,
            "usage": {"input_tokens": 40, "cache_read_input_tokens": 9000, "cache_creation_input_tokens": 1000, "output_tokens": 600}}
    return json.dumps({**base, **over})


STREAM = "\n".join([json.dumps({"type": "system", "subtype": "init"}), json.dumps({"type": "assistant", "message": {}}), result_line()])


def test_the_child_is_claude_code_as_shipped_but_cannot_load_the_persons_setup_or_call_gruntly(tmp_path):
    c = ClaudeAdapter().command(task(), tmp_path, "do the thing\nin two lines", None)
    a = c.argv
    assert a[1:3] == ["-p", "--model"] and a[3] == "haiku"
    assert "--setting-sources" in a and a[a.index("--setting-sources") + 1] == "project,local"   # not the user's plugins, hooks or MCP
    assert "--strict-mcp-config" in a and "--disable-slash-commands" in a
    assert a[a.index("--disallowedTools") + 1] == "Bash(gruntly *)"                                  # even if loaded, it cannot delegate
    assert "--bare" not in a                                                                         # --bare would end OAuth sign-in
    assert c.stdin == "do the thing\nin two lines"                                                   # the prompt never goes on the command line
    assert a[a.index("--output-format") + 1] == "stream-json" and "--verbose" in a


def test_the_model_defaults_to_haiku_and_a_named_one_is_used(tmp_path):
    a = ClaudeAdapter().command(task(model=""), tmp_path, "p", None).argv
    assert a[a.index("--model") + 1] == "haiku"
    a = ClaudeAdapter().command(task(model="sonnet"), tmp_path, "p", None).argv
    assert a[a.index("--model") + 1] == "sonnet"


def test_the_childs_permission_mode_follows_the_parents(tmp_path, monkeypatch):
    monkeypatch.delenv("GRUNTLY_PARENT_MODE", raising=False)
    a = ClaudeAdapter().command(task(), tmp_path, "p", None).argv
    assert a[a.index("--permission-mode") + 1] == "bypassPermissions"
    monkeypatch.setenv("GRUNTLY_PARENT_MODE", "acceptEdits")
    a = ClaudeAdapter().command(task(), tmp_path, "p", None).argv
    assert a[a.index("--permission-mode") + 1] == "acceptEdits"
    monkeypatch.setenv("GRUNTLY_PARENT_MODE", "plan")
    a = ClaudeAdapter().command(task(), tmp_path, "p", None).argv
    assert a[a.index("--permission-mode") + 1] == "plan"


def test_a_retry_resumes_the_session_and_a_spending_cap_is_always_set(tmp_path, monkeypatch):
    monkeypatch.delenv("GRUNTLY_CLAUDE_CHILD_MAX_USD", raising=False)
    a = ClaudeAdapter().command(task(), tmp_path, "p", "sess-9").argv
    assert a[a.index("--resume") + 1] == "sess-9"
    assert a[a.index("--max-budget-usd") + 1] == "0.50" and "--max-turns" in a
    monkeypatch.setenv("GRUNTLY_CLAUDE_CHILD_MAX_USD", "0.2")
    a = ClaudeAdapter().command(task(), tmp_path, "p", None).argv
    assert a[a.index("--max-budget-usd") + 1] == "0.20"
    monkeypatch.setenv("GRUNTLY_CLAUDE_CHILD_MAX_USD", "garbage")
    a = ClaudeAdapter().command(task(), tmp_path, "p", None).argv
    assert a[a.index("--max-budget-usd") + 1] == "0.50"


def test_the_result_event_gives_the_answer_the_session_and_the_dollars():
    o = ClaudeAdapter().parse(STREAM, "", 0)
    assert o.final_message == "Done.\nChanged utils.py." and o.session_id == "abc-123" and not o.is_error
    assert o.usage["cost_usd"] == 0.0123 and o.usage["requests"] == 7
    assert o.usage["input_tokens"] == 10040 and o.usage["output_tokens"] == 600 and o.usage["total_tokens"] == 10640


def test_running_out_of_turns_or_budget_is_an_error_even_with_exit_zero():
    for sub in ("error_max_turns", "error_max_budget_usd"):
        o = ClaudeAdapter().parse(result_line(subtype=sub, is_error=False, result=""), "", 0)
        assert o.is_error and o.final_message == sub.replace("_", " ")


def test_no_result_event_is_an_error_that_shows_stderr():
    o = ClaudeAdapter().parse("not json\n", "Invalid API key", 1)
    assert o.is_error and "Invalid API key" in o.final_message and not o.usage["available"]


def test_a_nonzero_exit_is_an_error_even_if_the_event_says_success():
    assert ClaudeAdapter().parse(STREAM, "", 1).is_error


def test_claude_is_a_known_harness_but_auto_never_picks_it():
    assert get_adapter("claude").name == "claude"
    assert "claude" in harnesses.HARNESSES and "claude" not in INSTALL_ORDER                  # a paid child must be chosen on purpose
    assert task().harness == "claude"


def test_the_cost_line_of_a_claude_child_says_it_is_paid_and_how_much():
    line = cost_line({"harness": "claude", "model": "haiku", "provider": "local", "requests": 7, "tokens": 10640, "s": 31, "cost_usd": 0.0123})
    assert "your Claude usage" in line and "$0.012" in line and "no paid tokens" not in line
    assert "not in your Claude usage" not in line
    assert "cost not reported" in cost_line({"harness": "claude", "model": "haiku", "provider": "local"})
    assert "no paid tokens" in cost_line({"harness": "hermes", "model": "m", "provider": "local"})      # the others are unchanged
