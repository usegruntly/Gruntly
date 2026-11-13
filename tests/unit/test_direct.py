"""The direct parent: which commands its one tool accepts, the loop against a stub chat endpoint with scripted tool calls (no key, no cost), the
usage and dollars it reports, and that it is registered as a delegating-only parent."""
import json
import os

import pytest

from gruntly import direct, parents, probe, providers
from gruntly.parents import base
from gruntly.parents import direct as dparent


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "cfg").mkdir()
    return tmp_path


@pytest.mark.parametrize("cmd,args,stdin", [
    ("gruntly agent-run 'Fix add()'", ["agent-run", "Fix add()"], None),
    ('gruntly agent-run --continue r_1 "make it handle empty input"', ["agent-run", "--continue", "r_1", "make it handle empty input"], None),
    ("gruntly agent-run 'line one\nline two; with a semicolon && an ampersand'", ["agent-run", "line one\nline two; with a semicolon && an ampersand"], None),
    ("gruntly agent-run --holdout - 'Fix it' <<'EOF'\ndef test_x():\n    assert 1 == 1 and (2 | 1)\nEOF", ["agent-run", "--holdout", "-", "Fix it"],
     "def test_x():\n    assert 1 == 1 and (2 | 1)\n"),
    ("gruntly status", ["status"], None)])
def test_one_gruntly_command_is_accepted_with_its_quoting_and_an_optional_heredoc(cmd, args, stdin):
    assert direct.parse_command(cmd) == (args, stdin)


@pytest.mark.parametrize("cmd,why", [
    ("echo hi", "only commands that start with `gruntly`"), ("", "only commands that start with `gruntly`"),
    ("cat note.txt | gruntly status", "only commands that start with `gruntly`"),
    ("gruntly status && rm -rf x", "`&&` is not allowed"), ("gruntly status; rm x", "`;` is not allowed"),
    ("gruntly status | cat", "`|` is not allowed"), ("gruntly status > out.txt", "`>` is not allowed"),
    ("gruntly status < in.txt", "`<` is not allowed"), ("gruntly status $(rm x)", "`(` is not allowed"),
    ("gruntly agent-run 'unclosed", "does not parse"),
    ("gruntly agent-run x <<'EOF'\nbody\n", "never closed"),
    ("gruntly agent-run x <<'EOF'\nbody\nEOF\nrm -rf y", "nothing may follow the heredoc")])
def test_anything_else_is_refused_with_the_reason(cmd, why):
    with pytest.raises(direct.Refused, match=why.replace("(", r"\(").replace("|", r"\|")):
        direct.parse_command(cmd)


def test_the_loop_runs_a_gruntly_command_feeds_the_result_back_and_stops_at_the_final_answer():
    ran = []
    replies = iter([
        {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
            "name": "bash", "arguments": json.dumps({"command": "gruntly agent-run 'Fix add()'"})}}]}}], "usage": {"prompt_tokens": 100, "completion_tokens": 20}},
        {"choices": [{"message": {"role": "assistant", "content": "passed: add() fixed"}}], "usage": {"prompt_tokens": 150, "completion_tokens": 10, "cost": 0.0004}}])
    seen = []

    def send(url, key, body):
        seen.append((url, key, body))
        return next(replies)

    out = direct.run_loop("the task", "http://h/v1/", "k", "m1", send=send, run=lambda args, stdin: ran.append((args, stdin)) or "=== GRUNTLY RESULT ===\nstatus: passed")
    assert ran == [(["agent-run", "Fix add()"], None)]
    assert out["final_message"] == "passed: add() fixed" and not out["is_error"] and out["turns"] == 2 and out["refused"] == 0
    assert out["usage"]["prompt"] == 250 and out["usage"]["completion"] == 30 and out["usage"]["requests"] == 2 and out["usage"]["cost_usd"] == 0.0004
    assert seen[0][0] == "http://h/v1/chat/completions" and seen[0][1] == "k" and seen[0][2]["model"] == "m1"
    assert [t["function"]["name"] for t in seen[0][2]["tools"]] == ["bash"] and seen[0][2]["messages"][0]["role"] == "system"
    msgs = seen[1][2]["messages"]                          # the same list the loop keeps appending to: the tool result sits before the final answer
    assert msgs[-2] == {"role": "tool", "tool_call_id": "c1", "content": "=== GRUNTLY RESULT ===\nstatus: passed"} and msgs[-1]["content"] == "passed: add() fixed"


def test_a_refused_command_is_told_to_the_model_and_nothing_runs_and_the_turn_limit_is_an_error():
    call = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "function": {"name": "bash", "arguments": json.dumps({"command": "rm -rf /"})}}]}}]}
    sent = []
    out = direct.run_loop("t", "http://h/v1", "k", "m", max_turns=3, send=lambda u, k, b: sent.append(b) or call,
                          run=lambda *a: pytest.fail("a refused command must not run"))
    assert out["is_error"] and "stopped after 3 turns" in out["final_message"] and out["refused"] == 3 and out["usage"]["missing"] == 3
    assert sent[1]["messages"][-1]["content"].startswith("refused: only commands that start with `gruntly`")


def test_an_endpoint_error_is_an_error_result_not_a_crash():
    def send(u, k, b):
        raise RuntimeError("HTTP 401 from the model: bad key")
    out = direct.run_loop("t", "http://h/v1", "k", "m", send=send)
    assert out["is_error"] and out["final_message"] == "HTTP 401 from the model: bad key" and out["turns"] == 0


def test_the_command_needs_a_provider_a_model_and_a_key_and_keeps_the_key_in_the_environment(cfg, monkeypatch):
    with pytest.raises(ValueError, match="needs --provider"):
        dparent.DirectParent().command("t", "delegating")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SECRET-xyz")
    c = dparent.DirectParent().command("Fix add().", "delegating", "meta/llama", "openrouter")
    assert c.argv[1:3] == ["-m", "gruntly.direct"] and c.argv[c.argv.index("--model") + 1] == "meta/llama" and c.argv[c.argv.index("--key-env") + 1] == "OPENROUTER_API_KEY"
    assert c.argv[c.argv.index("--base-url") + 1] == "https://openrouter.ai/api/v1" and c.stdin == "Fix add()."
    assert c.env == {"OPENROUTER_API_KEY": "sk-or-SECRET-xyz"} and "sk-or-SECRET-xyz" not in " ".join(c.argv)
    with pytest.raises(ValueError, match="only delegates"):
        dparent.DirectParent().command("t", "working", "m", "openrouter")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="no API key for groq"):
        dparent.provider_setup("groq", "m")
    c2 = dparent.DirectParent().command("t", "delegating", "qwen3:8b", "ollama")
    assert "--key-env" not in c2.argv and c2.env == {}


def test_the_result_line_is_read_for_the_reply_usage_and_turns():
    line = json.dumps({"final_message": "ok", "is_error": False, "turns": 2, "usage": {"prompt": 250, "completion": 30, "cached": 5, "requests": 2, "missing": 0, "cost_usd": None}})
    out = dparent.DirectParent().parse("noise\n" + line + "\n", "", 0)
    assert out.final_message == "ok" and not out.is_error and out.turns == 2 and (out.usage.prompt, out.usage.completion, out.usage.cached) == (250, 30, 5)
    assert dparent.DirectParent().parse("", "boom", 1).is_error and dparent.DirectParent().parse(line, "", 1).is_error


def test_it_is_registered_as_a_delegating_only_parent_that_needs_nothing_installed(monkeypatch):
    assert "direct" in parents.names()
    c = parents.get_parent("direct").capabilities()
    assert c.modes == ("delegating",) and c.replace_system_prompt and c.restrict_tools and c.restrict_shell and c.reports_usage and not c.reports_cost
    assert parents.get_parent("direct").detect().installed


def _fake_gruntly(tmp_path):
    d = tmp_path / "fakebin"
    d.mkdir()
    if os.name == "nt":
        (d / "gruntly.cmd").write_text("@echo off\r\necho usage: gruntly fake %*\r\n", encoding="utf8")
    else:
        (d / "gruntly").write_text('#!/bin/sh\necho "usage: gruntly fake $@"\n', encoding="utf8")
        (d / "gruntly").chmod(0o755)
    return {"PATH": str(d) + os.pathsep + os.environ["PATH"]}


@pytest.mark.parametrize("command,runs", [("gruntly status", True), ("echo hi > X.txt", False), ("gruntly status && echo hi > X.txt", False)])
def test_end_to_end_against_a_stub_model_the_gruntly_command_runs_and_every_other_is_refused(cfg, tmp_path, monkeypatch, command, runs):
    """The whole path as a launched parent: `python -m gruntly.direct`, a stub chat endpoint that asks for one command and then answers, the
    outcome read back with its token counts."""
    script = [{"tool": "bash", "args": {"command": command}}, "all done"]
    with probe.StubServer(script=script) as srv:
        monkeypatch.setitem(providers.ALL, "stubprov", providers.Provider(name="stubprov", base_url=srv.base_url, key_env="STUB_API_KEY", default_model="stub-model"))
        monkeypatch.setenv("STUB_API_KEY", "dummy-key-123")
        work = tmp_path / "work"
        work.mkdir()
        r = base.run(dparent.DirectParent(), "do it", "delegating", provider="stubprov", cwd=work, timeout_s=120, env=_fake_gruntly(tmp_path))
        assert r.returncode == 0 and not r.outcome.is_error and r.outcome.final_message == "all done", (r.stdout[-300:], r.stderr[-300:])
        turns = srv.chat()
        assert turns[0].tools == ["bash"] and turns[0].auth == "Bearer dummy-key-123" and turns[0].user == "do it" and len(turns) == 2
        result = turns[1].tool_results[0]
        assert ("usage: gruntly fake status" in result) if runs else result.startswith("refused:")
        assert not (work / "X.txt").exists()
        assert r.outcome.usage.requests == 2 and r.outcome.usage.prompt == 14 and r.outcome.turns == 2
        assert json.loads(r.stdout.strip().splitlines()[-1])["cost"]["source"] == "unknown"       # a provider with no price: unknown, never zero
