"""OpenCode as a parent: the lean config, provider and key plumbing, parsing, and (when OpenCode is installed) the real binary against a stub
model server that records what it sends."""
import json
import shutil
from pathlib import Path

import pytest

from gruntly import parents, probe, providers
from gruntly.parents import base, opencode, prompts

FIX = Path(__file__).parents[1] / "fixtures" / "opencode" / "run_json_success.jsonl"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "cfg").mkdir()
    return tmp_path


def test_the_lean_agent_denies_everything_but_gruntly_commands():
    c = opencode.lean_config()
    a = c["agent"]["gruntly"]
    assert c["default_agent"] == "gruntly" and a["mode"] == "primary" and a["prompt"] == prompts.DELEGATING and a["steps"] == opencode.STEPS
    perm = a["permission"]
    assert list(perm)[0] == "*" and perm["*"] == "deny"                      # first, so a tool nobody named (an MCP server's) is denied too
    for tool in ("read", "edit", "glob", "grep", "list", "task", "webfetch", "websearch", "skill", "lsp", "external_directory"):
        assert perm[tool] == "deny"
    assert perm["bash"] == {"*": "deny", "gruntly *": "allow"}


def test_the_delegating_command_is_lean_the_working_one_is_opencode_as_shipped(monkeypatch):
    monkeypatch.setattr(opencode, "which", lambda n: "/bin/opencode")
    d = opencode.OpenCodeParent().command("Fix add().", "delegating")
    assert d.argv == ["/bin/opencode", "run", "--format", "json", "--auto", "--pure"] and d.stdin == "Fix add()."
    cfg = json.loads(d.env["OPENCODE_CONFIG_CONTENT"])
    assert cfg["agent"]["gruntly"]["prompt"] == prompts.DELEGATING and "provider" not in cfg and len(d.notes) == 3
    w = opencode.OpenCodeParent().command("Fix add().", "working")
    assert w.argv == ["/bin/opencode", "run", "--format", "json", "--auto"] and w.notes == []
    assert "agent" not in json.loads(w.env["OPENCODE_CONFIG_CONTENT"])
    with pytest.raises(ValueError, match="mode must be one of"):
        opencode.OpenCodeParent().command("t", "lean")


def test_without_a_provider_the_harnesss_own_login_and_model_are_used(monkeypatch):
    monkeypatch.setattr(opencode, "which", lambda n: "/bin/opencode")
    c = opencode.OpenCodeParent().command("t", "delegating", "anthropic/claude-sonnet-5-5")
    assert c.argv[-2:] == ["-m", "anthropic/claude-sonnet-5-5"] and "OPENCODE_CONFIG_CONTENT" in c.env and len(c.env) == 1


def test_a_catalog_provider_becomes_an_openai_compatible_provider_with_its_key_in_the_environment_only(cfg, monkeypatch):
    monkeypatch.setattr(opencode, "which", lambda n: "/bin/opencode")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SECRET-xyz")
    c = opencode.OpenCodeParent().command("Fix it.", "delegating", "meta/llama", "openrouter")
    assert c.argv[-2:] == ["-m", "gruntly-openrouter/meta/llama"]
    conf = json.loads(c.env["OPENCODE_CONFIG_CONTENT"])
    blk = conf["provider"]["gruntly-openrouter"]
    assert blk["options"] == {"baseURL": "https://openrouter.ai/api/v1", "apiKey": "{env:OPENROUTER_API_KEY}"} and "meta/llama" in blk["models"]
    assert c.env["OPENROUTER_API_KEY"] == "sk-or-SECRET-xyz"
    assert "sk-or-SECRET-xyz" not in json.dumps(c.argv) and "sk-or-SECRET-xyz" not in c.env["OPENCODE_CONFIG_CONTENT"] and "sk-or-SECRET-xyz" not in (c.stdin or "")


def test_a_provider_that_cannot_be_used_is_a_clear_error_not_a_crash(cfg, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="no API key for openrouter: run `gruntly auth set openrouter`"):
        opencode.provider_setup("openrouter", "m")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    with pytest.raises(ValueError, match="provider groq has no default model: pass --model ID"):
        opencode.provider_setup("groq", None)
    with pytest.raises(ValueError, match="unknown provider 'nope'"):
        opencode.provider_setup("nope", "m")
    r = base.run(opencode.OpenCodeParent(), "t", "delegating", provider="openrouter", model="m")             # run() turns it into an error outcome
    assert r.returncode == 2 and r.outcome.is_error and "no API key" in r.outcome.final_message and r.command is None


def test_a_local_server_needs_no_key(cfg, monkeypatch):
    model, block, env = opencode.provider_setup("ollama", "qwen3:8b")
    assert model == "gruntly-ollama/qwen3:8b" and env == {} and block["gruntly-ollama"]["options"]["apiKey"] == "local"
    assert block["gruntly-ollama"]["options"]["baseURL"] == "http://127.0.0.1:11434/v1"


def test_the_recorded_run_is_read_for_the_reply_usage_and_turns():
    out = opencode.OpenCodeParent().parse(FIX.read_text(encoding="utf8"), "", 0)
    assert out.final_message and not out.is_error and out.usage.completion >= 0 and out.usage.prompt > 0 and out.turns
    assert opencode.OpenCodeParent().parse("not json", "boom", 1).is_error


def test_opencode_is_registered_and_reports_its_limits_honestly():
    assert "opencode" in parents.names()
    c = parents.get_parent("opencode").capabilities()
    assert (c.replace_system_prompt, c.restrict_tools, c.restrict_shell, c.reports_usage, c.reports_cost) == (True, True, True, True, False)
    assert any("title" in n for n in c.notes) and any("AGENTS.md" in n for n in c.notes)


@pytest.mark.skipif(not shutil.which("opencode"), reason="OpenCode is not installed")
def test_the_real_opencode_sends_our_prompt_and_only_a_bash_tool_and_the_key_reaches_it(cfg, tmp_path, monkeypatch):
    """No key, no cost: the real binary talks to a stub that records the request. Measured 2026-11-14 on 1.19.5: system prompt about 21,800
    characters and ten tools by default, about 1,900 characters and one tool (`bash`) here."""
    with probe.StubServer() as srv:
        stub = providers.Provider(name="stubprov", base_url=srv.base_url, key_env="STUB_API_KEY", default_model="stub-model")
        monkeypatch.setitem(providers.ALL, "stubprov", stub)
        monkeypatch.setenv("STUB_API_KEY", "dummy-key-123")
        work = tmp_path / "work"
        work.mkdir()
        state = tmp_path / "ocstate"
        env = {f"XDG_{k}_HOME": str(state / k.lower()) for k in ("DATA", "CONFIG", "STATE", "CACHE")}
        r = base.run(opencode.OpenCodeParent(), "Fix add().", "delegating", provider="stubprov", cwd=work, timeout_s=240, env=env)
        assert r.returncode == 0 and not r.outcome.is_error, (r.outcome.final_message, r.stderr[-300:])
        turn = max(srv.chat(), key=lambda s: len(s.tools))               # OpenCode also sends a tool-less request to title the session
        assert turn.tools == ["bash"]
        assert prompts.DELEGATING in turn.system and len(turn.system) < len(prompts.DELEGATING) + 800
        assert turn.auth == "Bearer dummy-key-123" and turn.user == "Fix add()."
        assert r.outcome.final_message == "ok"


@pytest.mark.skipif(not shutil.which("opencode"), reason="OpenCode is not installed")
@pytest.mark.parametrize("command,allowed", [("echo NOT_ALLOWED_MARKER", False), ("gruntly --help", True)])
def test_the_real_opencode_refuses_every_command_but_gruntly(cfg, tmp_path, monkeypatch, command, allowed):
    """The stub plays a model that asks for one shell command. Measured 2026-11-14 on 1.19.5: `echo` is refused with a permission message, and
    `gruntly --help` runs and returns gruntly's usage."""
    script = [{"tool": "bash", "args": {"command": command, "description": "probe"}}, "done"]
    with probe.StubServer(script=script) as srv:
        monkeypatch.setitem(providers.ALL, "stubprov", providers.Provider(name="stubprov", base_url=srv.base_url, key_env="STUB_API_KEY", default_model="stub-model"))
        monkeypatch.setenv("STUB_API_KEY", "dummy-key-123")
        work = tmp_path / "work"
        work.mkdir()
        env = {f"XDG_{k}_HOME": str(tmp_path / "ocstate" / k.lower()) for k in ("DATA", "CONFIG", "STATE", "CACHE")}
        r = base.run(opencode.OpenCodeParent(), "do it", "delegating", provider="stubprov", cwd=work, timeout_s=240, env=env)
        assert r.returncode == 0 and r.outcome.final_message == "done"
        results = [x for s in srv.chat() for x in s.tool_results]
        assert results, "the harness never answered the tool call"
        if allowed:
            assert "usage: gruntly" in results[0] and "NOT_ALLOWED_MARKER" not in results[0]
        else:
            assert "prevents you from using this specific tool call" in results[0]
