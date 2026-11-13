"""Hermes as a parent: the private folder (SOUL.md, a config with only gruntly's MCP tools and the lean settings, a key-less provider entry), parsing, `prepare`, and (when a Hermes
data folder with its dependency environment is named in GRUNTLY_TEST_HERMES_HOME) the real binary against a stub model server that records what it sends."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from gruntly import parents, probe, providers
from gruntly.parents import base, hermes, prompts

RESULT = json.dumps({"type": "result", "session_id": "local-abc", "exit_code": 0, "text": "ok",
                     "tokens": {"input": 7, "output": 1, "total": 8, "cache_read": 3, "cache_write": 0}, "duration_ms": 752})
STREAM = "\n".join([json.dumps({"type": "system", "subtype": "init", "model": "m", "session_id": ""}), json.dumps({"type": "text", "text": "ok"}), RESULT])
SHELL_AND_FILE_TOOLS = {"terminal", "read_file", "patch", "search_files", "write_file", "execute_code", "process", "browser_exec", "delegate_task"}


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("GRUNTLY_HERMES_PARENT_HOME", raising=False)
    (tmp_path / "cfg").mkdir()
    return tmp_path


def test_the_private_folder_is_per_mode_short_on_windows_and_can_be_named(cfg, monkeypatch):
    d, w = hermes.parent_home("delegating"), hermes.parent_home("working")
    assert d != w
    if os.name == "nt":
        assert d == Path.home() / ".ghp" / "d" and len(str(d)) < 40                # Hermes's environment nests ~200 characters deep: Windows stops at 260
    else:
        assert d == cfg / "state" / "hermes-parent" / "delegating"
    monkeypatch.setenv("GRUNTLY_HERMES_PARENT_HOME", str(cfg / "mine"))
    assert hermes.parent_home("delegating") == cfg / "mine" / "delegating"


def test_the_delegating_config_has_only_gruntlys_mcp_tools_tool_search_off_and_the_optional_prompt_sections_off(cfg, monkeypatch):
    monkeypatch.setattr(hermes, "find_hermes", lambda: "/bin/hermes")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SECRET-xyz")
    c = hermes.HermesParent().command("Fix add().", "delegating", "meta/llama", "openrouter")
    home = hermes.parent_home("delegating")
    a = c.argv
    assert a[:3] == ["/bin/hermes", "chat", "-Q"] and c.stdin == "Fix add()." and "--yolo" not in a and a[a.index("-t") + 1] == "mcp-gruntly" == hermes.TOOLSET
    assert "terminal" not in a and "--ignore-rules" not in a and a[a.index("--provider") + 1] == "custom:gruntly" and a[a.index("-m") + 1] == "meta/llama"
    assert c.files[str(home / "SOUL.md")] == prompts.DELEGATING_TOOL + hermes.REPO_SENTENCE and "{gruntly_cwd}" in hermes.REPO_SENTENCE and c.env["HERMES_HOME"] == str(home) and len(c.notes) == 3
    conf = yaml.safe_load(c.files[str(home / "config.yaml")])
    assert conf["custom_providers"][0]["key_env"] == "OPENROUTER_API_KEY" and conf["custom_providers"][0]["base_url"] == "https://openrouter.ai/api/v1"
    srv = conf["mcp_servers"]["gruntly"]
    assert srv["command"] == sys.executable and srv["args"] == ["-m", "gruntly", "mcp"]
    assert srv["env"] == {"GRUNTLY_MCP_REQUIRE_REPO": "1"}
    assert srv["tools"] == {"include": ["gruntly_delegate", "gruntly_manage"], "prompts": False, "resources": False}
    assert conf["gateway"] == {"unmanaged_idle_exit_seconds": 2} and conf["tools"]["tool_search"]["enabled"] == "off" and conf["memory"] == {"memory_enabled": False, "user_profile_enabled": False}
    ag = conf["agent"]
    assert all(ag[k] is False for k in ("tool_use_enforcement", "execution_guidance", "task_completion_guidance", "parallel_tool_call_guidance", "environment_probe", "bot_mode_protocol"))
    assert ag["coding_context"] == "off" and conf["platform_hints"] == {"cli": {"replace": ""}}
    assert "sk-or-SECRET-xyz" not in "".join(c.files.values()) and c.env["OPENROUTER_API_KEY"] == "sk-or-SECRET-xyz" and "sk-or-SECRET-xyz" not in " ".join(a)


def test_the_tool_variant_of_the_prompt_names_the_tools_and_has_no_shell_in_it():
    t = prompts.DELEGATING_TOOL
    assert "gruntly_delegate" in t and "gruntly_manage" in t and "follow_up_run_id" in t and "GRUNTLY-FALLBACK" in t
    assert "Bash" not in t and "agent-run" not in t and "terminal" not in t.lower() and '"' not in t and "<" not in t and "Do not read files yourself" in t
    assert prompts.DELEGATING != t and "Bash" in prompts.DELEGATING                              # the measured prompt is untouched


def test_the_working_command_is_hermes_as_shipped_with_yolo_and_its_own_config(cfg, monkeypatch):
    monkeypatch.setattr(hermes, "find_hermes", lambda: "/bin/hermes")
    c = hermes.HermesParent().command("Fix add().", "working")
    assert "--yolo" in c.argv and "-t" not in c.argv and c.files == {} and "HERMES_HOME" not in c.env and c.notes == []
    w = hermes.HermesParent().command("t", "working", "m", "ollama")
    conf = yaml.safe_load(w.files[str(hermes.parent_home("working") / "config.yaml")])
    assert "mcp_servers" not in conf and "tools" not in conf and "SOUL.md" not in " ".join(w.files)         # the working folder never carries the lean parts
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
    r = base.run(hermes.HermesParent(), "t", "delegating")                        # no provider: the private folder has none of your logins
    assert r.returncode == 2 and r.outcome.is_error and "needs --provider" in r.outcome.final_message


def test_the_stream_json_result_is_read_for_the_reply_usage_with_cache_and_session():
    out = hermes.HermesParent().parse(STREAM, "session_id: local-abc\n", 0)
    assert out.final_message == "ok" and not out.is_error and out.session_id == "local-abc"
    assert (out.usage.prompt, out.usage.completion, out.usage.cached) == (7, 1, 3)


def test_a_failed_run_is_an_error_and_a_missing_dependency_environment_says_how_to_fix_it():
    e = hermes.HermesParent().parse("", "hermes: no dependency environment is committed for this install; run `hermes pm repair`", 1)
    assert e.is_error and "gruntly parent prepare hermes" in e.final_message
    assert hermes.HermesParent().parse("boom", "", 1).is_error


def test_prepare_runs_hermes_pm_repair_with_the_private_folder_as_its_home(cfg, monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"], seen["home"] = argv, kw["env"]["HERMES_HOME"]
        return subprocess.CompletedProcess(argv, 0, stdout="  Installing Python dependencies\nhermes: dependency environment repaired\n", stderr="")
    monkeypatch.setattr(hermes, "find_hermes", lambda: "/bin/hermes")
    monkeypatch.setattr(hermes.subprocess, "run", fake_run)
    ok, tail = hermes.prepare()
    assert ok and seen["argv"] == ["/bin/hermes", "pm", "repair"] and seen["home"] == str(hermes.parent_home("delegating")) and hermes.parent_home("delegating").is_dir()
    assert "repaired" in tail
    monkeypatch.setattr(hermes.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr="boom"))
    assert hermes.prepare()[0] is False
    monkeypatch.setattr(hermes, "find_hermes", lambda: None)
    assert hermes.prepare()[0] is False


def test_hermes_is_registered_and_reports_a_shell_free_lean_setup_checked_live():
    assert "hermes" in parents.names()
    c = parents.get_parent("hermes").capabilities()
    assert (c.replace_system_prompt, c.restrict_tools, c.restrict_shell, c.disable_extensions, c.reports_usage, c.reports_cost) == (False, True, True, True, True, False)
    assert any("no shell" in n for n in c.notes) and any("3,200" in n for n in c.notes) and not c.experimental


PREPARED = os.environ.get("GRUNTLY_TEST_HERMES_HOME")


def _use_stub(srv, monkeypatch):
    monkeypatch.setitem(providers.ALL, "stubprov", providers.Provider(name="stubprov", base_url=srv.base_url, key_env="STUB_API_KEY", default_model="stub-model"))
    monkeypatch.setenv("STUB_API_KEY", "dummy-key-123")
    monkeypatch.setattr(hermes, "parent_home", lambda mode="delegating": Path(PREPARED))           # a folder that already has its dependency environment


@pytest.mark.skipif(not PREPARED or not hermes.find_hermes(), reason="set GRUNTLY_TEST_HERMES_HOME to a Hermes folder prepared with `hermes pm repair`")
def test_the_real_hermes_offers_only_gruntlys_tools_and_our_prompt_and_a_call_reaches_gruntlys_mcp_server(cfg, tmp_path, monkeypatch):
    """No key, no cost. Measured 2026-11-13 on 0.23.0: 20 tools and about 9,900 characters by default; here 6 tools (gruntly's two and four inert MCP helpers), no shell,
    about 4,900 characters with ours at the head and the launch folder named. A scripted gruntly_delegate call without `repo` is refused by gruntly's own MCP server."""
    with probe.StubServer(script=[{"tool": "mcp__gruntly__gruntly_delegate", "args": {"request": "Fix add()"}}, "done"]) as srv:
        _use_stub(srv, monkeypatch)
        work = tmp_path / "work"
        work.mkdir()
        r = base.run(hermes.HermesParent(), "Fix add().", "delegating", provider="stubprov", cwd=work, timeout_s=300)
        assert r.returncode == 0 and not r.outcome.is_error and r.outcome.final_message == "done", (r.outcome.final_message, r.stderr[-300:])
        turn = max(srv.chat(), key=lambda s: len(s.tools))                    # Hermes also makes a tool-less request of its own
        names = set(turn.tools)
        assert {"mcp__gruntly__gruntly_delegate", "mcp__gruntly__gruntly_manage"} <= names and len(names) <= 6
        assert not names & SHELL_AND_FILE_TOOLS and all(n.startswith("mcp__gruntly__") for n in names)         # no shell and no file tool exists
        assert turn.system.startswith(prompts.DELEGATING_TOOL.strip()) and len(turn.system) < len(prompts.DELEGATING_TOOL) + 4300
        assert work.resolve().as_posix() in turn.system and "{gruntly_cwd}" not in turn.system                 # the launch folder was written into the prompt
        results = [x for s in srv.chat() for x in s.tool_results]
        assert results and "repo is required" in results[0]                                       # gruntly's MCP server answered, and refuses to guess the repository
        assert r.outcome.usage is not None
