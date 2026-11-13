"""Hermes as a parent: the private folder with SOUL.md and a key-less config, parsing, and (when a Hermes data folder with its dependency
environment is named in GRUNTLY_TEST_HERMES_HOME) the real binary against a stub model server that records what it sends."""
import json
import os
from pathlib import Path

import pytest

from gruntly import parents, probe, providers
from gruntly.parents import base, hermes, prompts

RESULT = json.dumps({"type": "result", "session_id": "local-abc", "exit_code": 0, "text": "ok",
                     "tokens": {"input": 7, "output": 1, "total": 8, "cache_read": 0, "cache_write": 0}, "duration_ms": 752})
STREAM = "\n".join([json.dumps({"type": "system", "subtype": "init", "model": "m", "session_id": ""}), json.dumps({"type": "text", "text": "ok"}), RESULT])


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("GRUNTLY_HERMES_PARENT_HOME", raising=False)
    (tmp_path / "cfg").mkdir()
    return tmp_path


def test_the_private_folder_is_per_mode_and_can_be_named(cfg, monkeypatch):
    assert hermes.parent_home("delegating") == cfg / "state" / "hermes-parent" / "delegating"
    assert hermes.parent_home("working") != hermes.parent_home("delegating")
    monkeypatch.setenv("GRUNTLY_HERMES_PARENT_HOME", str(cfg / "mine"))
    assert hermes.parent_home("delegating") == cfg / "mine" / "delegating"


def test_the_delegating_command_puts_our_prompt_in_soul_md_and_leaves_the_terminal_toolset(cfg, monkeypatch):
    monkeypatch.setattr(hermes, "find_hermes", lambda: "/bin/hermes")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SECRET-xyz")
    c = hermes.HermesParent().command("Fix add().", "delegating", "meta/llama", "openrouter")
    home = hermes.parent_home("delegating")
    a = c.argv
    assert a[:3] == ["/bin/hermes", "chat", "-Q"] and c.stdin == "Fix add()." and a[a.index("-t") + 1] == "terminal" and "--yolo" not in a
    assert a[a.index("--provider") + 1] == "custom:gruntly" and a[a.index("-m") + 1] == "meta/llama" and "--ignore-rules" not in a
    assert c.files[str(home / "SOUL.md")] == prompts.DELEGATING and c.env["HERMES_HOME"] == str(home) and len(c.notes) == 4
    conf = c.files[str(home / "config.yaml")]
    assert 'key_env: "OPENROUTER_API_KEY"' in conf and 'base_url: "https://openrouter.ai/api/v1"' in conf and "sk-or-SECRET-xyz" not in conf
    assert c.env["OPENROUTER_API_KEY"] == "sk-or-SECRET-xyz" and "sk-or-SECRET-xyz" not in " ".join(a)


def test_the_working_command_is_hermes_as_shipped_with_yolo(cfg, monkeypatch):
    monkeypatch.setattr(hermes, "find_hermes", lambda: "/bin/hermes")
    c = hermes.HermesParent().command("Fix add().", "working")
    assert "--yolo" in c.argv and "-t" not in c.argv and c.files == {} and "HERMES_HOME" not in c.env and c.notes == []
    with pytest.raises(ValueError, match="mode must be one of"):
        hermes.HermesParent().command("t", "lean")


def test_a_local_server_needs_no_key_and_a_provider_that_cannot_be_used_is_a_clear_error(cfg, monkeypatch):
    text, model, env = hermes.provider_setup("ollama", "qwen3:8b")
    assert 'api_key: "local"' in text and "key_env" not in text and model == "qwen3:8b" and env == {}
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    with pytest.raises(ValueError, match="no API key for openrouter"):
        hermes.provider_setup("openrouter", "m")
    with pytest.raises(ValueError, match="provider groq has no default model"):
        hermes.provider_setup("groq", None)
    with pytest.raises(ValueError, match="unknown provider 'nope'"):
        hermes.provider_setup("nope", "m")
    r = base.run(hermes.HermesParent(), "t", "delegating")                        # no provider and no login in the private folder
    assert r.returncode == 2 and r.outcome.is_error and "needs --provider" in r.outcome.final_message


def test_the_stream_json_result_is_read_for_the_reply_usage_and_session():
    out = hermes.HermesParent().parse(STREAM, "session_id: local-abc\n", 0)
    assert out.final_message == "ok" and not out.is_error and out.session_id == "local-abc"
    assert (out.usage.prompt, out.usage.completion) == (7, 1)


def test_a_failed_run_is_an_error_and_a_missing_dependency_environment_says_how_to_fix_it():
    e = hermes.HermesParent().parse("", "hermes: no dependency environment is committed for this install; run `hermes pm repair`", 1)
    assert e.is_error and "hermes pm repair" in e.final_message and "HERMES_HOME" in e.final_message
    assert hermes.HermesParent().parse("boom", "", 1).is_error


def test_hermes_is_registered_and_reports_its_limits_honestly():
    assert "hermes" in parents.names()
    c = parents.get_parent("hermes").capabilities()
    assert (c.replace_system_prompt, c.restrict_tools, c.restrict_shell, c.reports_usage, c.reports_cost) == (False, True, False, True, False)
    assert any("5,300" in n for n in c.notes) and any("not restricted" in n for n in c.notes) and c.experimental


PREPARED = os.environ.get("GRUNTLY_TEST_HERMES_HOME")


def _use_stub(srv, monkeypatch):
    monkeypatch.setitem(providers.ALL, "stubprov", providers.Provider(name="stubprov", base_url=srv.base_url, key_env="STUB_API_KEY", default_model="stub-model"))
    monkeypatch.setenv("STUB_API_KEY", "dummy-key-123")
    monkeypatch.setattr(hermes, "parent_home", lambda mode="delegating": Path(PREPARED))           # a folder that already has its dependency environment


@pytest.mark.skipif(not PREPARED or not hermes.find_hermes(), reason="set GRUNTLY_TEST_HERMES_HOME to a Hermes folder prepared with `hermes pm repair`")
def test_the_real_hermes_has_our_identity_and_the_terminal_toolset(cfg, tmp_path, monkeypatch):
    """No key, no cost. Measured 2026-11-14 on 0.23.0: twenty tools and about 9,900 characters by default; four tools (terminal plus three
    tool-lookup tools) and about 6,250 characters here, ours at the head in place of Hermes's identity."""
    with probe.StubServer() as srv:
        _use_stub(srv, monkeypatch)
        work = tmp_path / "work"
        work.mkdir()
        r = base.run(hermes.HermesParent(), "Fix add().", "delegating", provider="stubprov", cwd=work, timeout_s=300)
        assert r.returncode == 0 and not r.outcome.is_error, (r.outcome.final_message, r.stderr[-300:])
        turn = max(srv.chat(), key=lambda s: len(s.tools))                    # Hermes also makes a tool-less request of its own
        assert "terminal" in turn.tools and len(turn.tools) <= 4 and "read_file" not in turn.tools and "patch" not in turn.tools
        assert turn.system.startswith(prompts.DELEGATING.strip()) and len(turn.system) < len(prompts.DELEGATING) + 5800
        assert "Fix add()." in turn.user and turn.auth in ("Bearer no-key-required", "Bearer dummy-key-123")   # a local endpoint always gets the placeholder
        assert r.outcome.final_message == "ok" and r.outcome.usage is not None
