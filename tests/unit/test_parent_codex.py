"""Codex CLI as a parent: the lean flags and files, provider and key plumbing, parsing, and (when Codex is installed, on PATH or named in
GRUNTLY_TEST_CODEX) the real binary against a stub model server that speaks the Responses API and records what it sends."""
import json
import os
import shutil
import sys

import pytest

from gruntly import parents, probe, providers
from gruntly.parents import base, codex, prompts

REAL = os.environ.get("GRUNTLY_TEST_CODEX") or shutil.which("codex")
EVENTS = "\n".join(json.dumps(e) for e in [
    {"type": "thread.started", "thread_id": "01a1d254"},
    {"type": "item.completed", "item": {"id": "item_0", "type": "error", "message": "Model metadata for `stub-model` not found."}},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "ok"}},
    {"type": "turn.completed", "usage": {"input_tokens": 7, "cached_input_tokens": 2, "cache_write_input_tokens": 0, "output_tokens": 1}}])


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("GRUNTLY_CODEX_PARENT_HOME", raising=False)
    (tmp_path / "cfg").mkdir()
    monkeypatch.setattr(codex, "which", lambda n: REAL or "/bin/codex")
    return tmp_path


def _pairs(argv, flag):
    return [argv[i + 1] for i, a in enumerate(argv) if a == flag]


def test_the_delegating_command_writes_our_prompt_and_one_rule_and_goes_read_only_with_no_approvals(cfg, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SECRET-xyz")
    c = codex.CodexParent().command("Fix add().", "delegating", "gpt-x", "openai")
    home = codex.parent_home("delegating")
    a = c.argv
    assert a[1:4] == ["exec", "--skip-git-repo-check", "--json"] and a[-1] == "-" and c.stdin == "Fix add()." and "--ephemeral" in a
    assert _pairs(a, "-s") == ["read-only"] and 'approval_policy="never"' in _pairs(a, "-c") and _pairs(a, "-m") == ["gpt-x"]
    assert set(_pairs(a, "--disable")) == set(codex.FEATURES_OFF) and 'web_search="disabled"' in _pairs(a, "-c") and "skills.bundled.enabled=false" in _pairs(a, "-c")
    assert "model_instructions_file=" + json.dumps(str(home / "instructions.md")) in _pairs(a, "-c")
    assert c.files[str(home / "instructions.md")] == prompts.DELEGATING
    assert c.files[str(home / "rules" / "default.rules")] == 'prefix_rule(pattern = ["gruntly"], decision = "allow")\n'
    assert c.env["CODEX_HOME"] == str(home) and len(c.notes) == 2
    prov = [x for x in _pairs(a, "-c") if x.startswith("model_providers.gruntly_openai=")][0]
    assert 'env_key = "OPENAI_API_KEY"' in prov and 'wire_api = "responses"' in prov and 'base_url = "https://api.openai.com/v1"' in prov
    assert c.env["OPENAI_API_KEY"] == "sk-SECRET-xyz" and "sk-SECRET-xyz" not in " ".join(a) and "sk-SECRET-xyz" not in "".join(c.files.values())


def test_the_working_command_is_codex_as_shipped_with_the_workspace_sandbox_and_no_prompts(cfg):
    c = codex.CodexParent().command("Fix add().", "working")
    assert "--disable" not in c.argv and "model_instructions_file" not in " ".join(c.argv) and c.files == {} and "CODEX_HOME" not in c.env and c.notes == []
    assert _pairs(c.argv, "-s") == ["workspace-write"] and 'approval_policy="never"' in _pairs(c.argv, "-c") and "--ephemeral" not in c.argv
    with pytest.raises(ValueError, match="mode must be one of"):
        codex.CodexParent().command("t", "lean")


def test_a_provider_without_the_responses_api_is_refused_and_one_nobody_knows_is_noted(cfg, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    with pytest.raises(ValueError, match=r"deepseek does not serve the Responses API.*openai"):
        codex.provider_setup("deepseek", "m")
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    flags, model, env, notes = codex.provider_setup("mistral", "m")
    assert model == "m" and any("not known" in n for n in notes) and env == {"MISTRAL_API_KEY": "k"}


def test_a_local_server_needs_no_key_and_a_provider_that_cannot_be_used_is_a_clear_error(cfg, monkeypatch):
    flags, model, env, notes = codex.provider_setup("ollama", "qwen3:8b")
    assert env == {} and model == "qwen3:8b" and "env_key" not in " ".join(flags) and notes == []
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    with pytest.raises(ValueError, match="no API key for openrouter"):
        codex.provider_setup("openrouter", "m")
    with pytest.raises(ValueError, match="provider groq has no default model"):
        codex.provider_setup("groq", None)
    with pytest.raises(ValueError, match="unknown provider 'nope'"):
        codex.provider_setup("nope", "m")
    r = base.run(codex.CodexParent(), "t", "delegating")                          # no provider: its private folder has no ChatGPT login
    assert r.returncode == 2 and r.outcome.is_error and "needs --provider" in r.outcome.final_message


def test_the_events_are_read_for_the_reply_usage_and_session_and_a_warning_is_not_a_failure():
    out = codex.CodexParent().parse(EVENTS, "", 0)
    assert out.final_message == "ok" and not out.is_error and out.session_id == "01a1d254" and out.turns == 1
    assert (out.usage.prompt, out.usage.completion, out.usage.cached) == (7, 1, 2)
    bad = codex.CodexParent().parse(json.dumps({"type": "turn.failed", "error": {"message": "quota"}}), "", 1)
    assert bad.is_error and bad.final_message == "quota"
    assert codex.CodexParent().parse("", "boom", 1).is_error and codex.CodexParent().parse("", "", 1).final_message == "no output"


def test_codex_is_registered_and_reports_its_limits_honestly():
    assert "codex" in parents.names()
    c = parents.get_parent("codex").capabilities()
    assert (c.replace_system_prompt, c.restrict_tools, c.restrict_shell, c.reports_usage, c.reports_cost) == (True, False, True, True, False)
    assert any("request_user_input" in n for n in c.notes) and any("Responses API" in n for n in c.notes)


def _stub(srv, monkeypatch, tmp_path):
    monkeypatch.setitem(providers.ALL, "stubprov", providers.Provider(name="stubprov", base_url=srv.base_url, key_env="STUB_API_KEY",
                                                                       default_model="stub-model", responses_api=True))
    monkeypatch.setenv("STUB_API_KEY", "dummy-key-123")
    monkeypatch.setenv("GRUNTLY_CODEX_PARENT_HOME", str(tmp_path / "codexhome"))
    work = tmp_path / "work"
    work.mkdir()
    (work / "note.txt").write_text("SECRET_CONTENT", encoding="utf8")
    return work


def _fake_gruntly(tmp_path, outside):
    """A stand-in `gruntly` that prints a usage line and writes a file OUTSIDE the workspace, as the real one does with its worktrees."""
    d = tmp_path / "fakebin"
    d.mkdir()
    if os.name == "nt":
        (d / "gruntly.cmd").write_text(f"@echo off\r\necho wrote > \"{outside}\"\r\necho usage: gruntly fake\r\n", encoding="utf8")
    else:
        f = d / "gruntly"
        f.write_text(f"#!/bin/sh\necho wrote > '{outside}'\necho usage: gruntly fake\n", encoding="utf8")
        f.chmod(0o755)
    return {"PATH": str(d) + os.pathsep + os.environ["PATH"]}


@pytest.mark.skipif(not REAL, reason="Codex is not installed (set GRUNTLY_TEST_CODEX to a codex executable)")
def test_the_real_codex_sends_exactly_our_prompt_and_a_short_tool_list_and_the_key_reaches_it(cfg, tmp_path, monkeypatch):
    """No key, no cost. Measured 2026-11-14 on 0.167.2: nine tools and about 19,500 characters of instructions by default; four tools and
    exactly our 1,548 characters here (the prompt comes as the first developer message)."""
    with probe.StubServer() as srv:
        work = _stub(srv, monkeypatch, tmp_path)
        r = base.run(codex.CodexParent(), "Fix add().", "delegating", provider="stubprov", cwd=work, timeout_s=240)
        assert r.returncode == 0 and not r.outcome.is_error, (r.outcome.final_message, r.stderr[-300:])
        turn = srv.chat()[0]
        assert turn.system.strip() == prompts.DELEGATING.strip()
        assert "exec_command" in turn.tools and len(turn.tools) <= 4 and not {"web_search", "multi_agent_v1", "create_goal"} & set(turn.tools)
        assert turn.auth == "Bearer dummy-key-123" and turn.user == "Fix add()." and r.outcome.final_message == "ok"


@pytest.mark.skipif(not REAL, reason="Codex is not installed (set GRUNTLY_TEST_CODEX to a codex executable)")
@pytest.mark.parametrize("command,marker,runs", [("gruntly --help", None, True), ("echo hi > WRITE_MARKER.txt", "WRITE_MARKER.txt", False),
                                                  ("cat note.txt", None, False), ("gruntly --help && echo hi > CHAIN_MARKER.txt", "CHAIN_MARKER.txt", False)])
def test_the_real_codex_runs_gruntly_outside_its_sandbox_and_blocks_every_other_command(cfg, tmp_path, monkeypatch, command, marker, runs):
    """The stub plays a model that asks for one command. Measured on 0.167.2: `gruntly` runs and may write outside the workspace (the rule
    takes it out of the read-only sandbox); a write, a read and a chained command are all `blocked by policy`."""
    script = [{"tool": "exec_command", "args": {"cmd": command}}, "done"]
    with probe.StubServer(script=script) as srv:
        work = _stub(srv, monkeypatch, tmp_path)
        outside = tmp_path / "OUTSIDE.txt"
        r = base.run(codex.CodexParent(), "do it", "delegating", provider="stubprov", cwd=work, timeout_s=240, env=_fake_gruntly(tmp_path, outside))
        assert r.returncode == 0 and r.outcome.final_message == "done"
        results = [x for s in srv.chat() for x in s.tool_results]
        assert results, "the harness never answered the tool call"
        if runs:
            assert "usage: gruntly fake" in results[0] and outside.exists()
        else:
            assert "blocked by policy" in results[0] and "SECRET_CONTENT" not in results[0] and not outside.exists()
        if marker:
            assert not (work / marker).exists()
