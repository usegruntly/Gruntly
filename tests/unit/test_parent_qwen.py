"""Qwen Code as a parent: the lean flags, provider and key plumbing, parsing, and (when Qwen Code is installed) the real binary against a stub
model server that records what it sends."""
import shutil
from pathlib import Path

import pytest

from gruntly import parents, probe, providers
from gruntly.parents import base, prompts, qwen

FIX = Path(__file__).parents[1] / "fixtures" / "qwen" / "headless_json_success.json"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "cfg").mkdir()
    return tmp_path


def _flag(argv, name):
    """The values after a flag, up to the next flag."""
    i = argv.index(name) + 1
    out = []
    while i < len(argv) and not argv[i].startswith("-"):
        out.append(argv[i])
        i += 1
    return out


def test_the_delegating_command_is_bare_with_our_prompt_one_tool_and_a_gruntly_only_allow_rule(monkeypatch):
    monkeypatch.setattr(qwen, "which", lambda n: "/bin/qwen")
    c = qwen.QwenParent().command("Fix add().", "delegating")
    a = c.argv
    assert a[0] == "/bin/qwen" and "--bare" in a and c.stdin == "Fix add()."
    assert _flag(a, "--system-prompt") == [prompts.DELEGATING]
    assert _flag(a, "--allowed-tools") == ["run_shell_command(gruntly)"] and _flag(a, "--approval-mode") == ["default"]
    assert set(_flag(a, "--exclude-tools")) == set(qwen.EXCLUDED) and "run_shell_command" not in qwen.EXCLUDED
    assert _flag(a, "--max-session-turns") == [str(qwen.TURNS)] and "-m" not in a and len(c.notes) == 2


def test_the_working_command_is_qwen_as_shipped_with_every_tool_approved(monkeypatch):
    monkeypatch.setattr(qwen, "which", lambda n: "/bin/qwen")
    c = qwen.QwenParent().command("Fix add().", "working", "qwen3-coder")
    assert "--bare" not in c.argv and "--system-prompt" not in c.argv and "--exclude-tools" not in c.argv and c.notes == []
    assert _flag(c.argv, "--approval-mode") == ["yolo"] and c.argv[c.argv.index("-m") + 1] == "qwen3-coder"
    with pytest.raises(ValueError, match="mode must be one of"):
        qwen.QwenParent().command("t", "lean")


def test_a_catalog_provider_is_an_openai_endpoint_with_its_key_in_the_environment_only(cfg, monkeypatch):
    monkeypatch.setattr(qwen, "which", lambda n: "/bin/qwen")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SECRET-xyz")
    c = qwen.QwenParent().command("Fix it.", "delegating", "meta/llama", "openrouter")
    assert _flag(c.argv, "--auth-type") == ["openai"] and c.argv[c.argv.index("-m") + 1] == "meta/llama"
    assert c.env["OPENAI_BASE_URL"] == "https://openrouter.ai/api/v1" and c.env["OPENAI_API_KEY"] == "sk-or-SECRET-xyz"
    assert "sk-or-SECRET-xyz" not in " ".join(c.argv) and "sk-or-SECRET-xyz" not in (c.stdin or "")


def test_a_provider_that_cannot_be_used_is_a_clear_error_not_a_crash(cfg, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    with pytest.raises(ValueError, match="no API key for openrouter"):
        qwen.provider_setup("openrouter", "m")
    with pytest.raises(ValueError, match="provider groq has no default model"):
        qwen.provider_setup("groq", None)
    with pytest.raises(ValueError, match="unknown provider 'nope'"):
        qwen.provider_setup("nope", "m")
    flags, env = qwen.provider_setup("ollama", "qwen3:8b")
    assert flags[-1] == "qwen3:8b" and env["OPENAI_API_KEY"] == "local" and env["OPENAI_BASE_URL"] == "http://127.0.0.1:11434/v1"
    r = base.run(qwen.QwenParent(), "t", "delegating", provider="openrouter", model="m")
    assert r.returncode == 2 and r.outcome.is_error and r.command is None


def test_the_recorded_run_is_read_for_the_reply_and_usage():
    out = qwen.QwenParent().parse(FIX.read_text(encoding="utf8"), "", 0)
    assert out.final_message and not out.is_error and out.usage is not None and out.usage.prompt > 0
    assert qwen.QwenParent().parse("not json", "boom", 1).is_error


def test_qwen_is_registered_and_reports_its_limits_honestly():
    assert "qwen" in parents.names()
    c = parents.get_parent("qwen").capabilities()
    assert (c.replace_system_prompt, c.restrict_tools, c.restrict_shell, c.reports_usage, c.reports_cost) == (True, True, True, True, False)
    assert any("echo" in n for n in c.notes) and any("--bare" in n for n in c.notes)


def _stub_env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {"HOME": str(home), "USERPROFILE": str(home)}                       # Qwen reads its settings and login from the home folder


def _use_stub(srv, monkeypatch):
    monkeypatch.setitem(providers.ALL, "stubprov", providers.Provider(name="stubprov", base_url=srv.base_url, key_env="STUB_API_KEY", default_model="stub-model"))
    monkeypatch.setenv("STUB_API_KEY", "dummy-key-123")


@pytest.mark.skipif(not shutil.which("qwen"), reason="Qwen Code is not installed")
def test_the_real_qwen_sends_our_prompt_and_only_a_shell_tool_and_the_key_reaches_it(cfg, tmp_path, monkeypatch):
    """No key, no cost. Measured 2026-11-14 on 0.26.9: six tools by default under --bare, one (`run_shell_command`) with the exclude list;
    the system prompt is exactly ours."""
    with probe.StubServer() as srv:
        _use_stub(srv, monkeypatch)
        work = tmp_path / "work"
        work.mkdir()
        r = base.run(qwen.QwenParent(), "Fix add().", "delegating", provider="stubprov", cwd=work, timeout_s=240, env=_stub_env(tmp_path))
        assert r.returncode == 0 and not r.outcome.is_error, (r.outcome.final_message, r.stderr[-300:])
        turn = srv.chat()[0]
        assert turn.tools == ["run_shell_command"]
        assert turn.system.strip() == prompts.DELEGATING.strip()
        assert turn.auth == "Bearer dummy-key-123" and "Fix add()." in turn.user
        assert r.outcome.final_message == "ok"


@pytest.mark.skipif(not shutil.which("qwen"), reason="Qwen Code is not installed")
@pytest.mark.parametrize("command,marker,runs", [("gruntly --help", None, True), ("touch WRITE_MARKER.txt", "WRITE_MARKER.txt", False),
                                                  ("cat note.txt", None, False), ("gruntly --help && touch CHAIN_MARKER.txt", "CHAIN_MARKER.txt", False),
                                                  ("python -c \"open('PY_MARKER.txt','w').write('x')\"", "PY_MARKER.txt", False)])
def test_the_real_qwen_runs_gruntly_and_refuses_commands_that_write_read_or_chain(cfg, tmp_path, monkeypatch, command, marker, runs):
    """The stub plays a model that asks for one shell command. Measured on 0.26.9: gruntly runs; `touch`, redirects and `cat` are denied by
    the permission rules of the excluded tools, a chained command is denied as a whole, and an interpreter is declined (headless mode cannot
    ask). `echo` is the one harmless command that still runs, so it is not tested as refused."""
    script = [{"tool": "run_shell_command", "args": {"command": command, "description": "probe", "is_background": False}}, "done"]
    with probe.StubServer(script=script) as srv:
        _use_stub(srv, monkeypatch)
        work = tmp_path / "work"
        work.mkdir()
        (work / "note.txt").write_text("SECRET_CONTENT", encoding="utf8")
        r = base.run(qwen.QwenParent(), "do it", "delegating", provider="stubprov", cwd=work, timeout_s=240, env=_stub_env(tmp_path))
        assert r.returncode == 0 and r.outcome.final_message == "done"
        results = [x for s in srv.chat() for x in s.tool_results]
        assert results, "the harness never answered the tool call"
        if runs:
            assert "usage: gruntly" in results[0]
        else:
            assert "SECRET_CONTENT" not in results[0] and ("denied" in results[0] or "declined" in results[0])
        if marker:
            assert not (work / marker).exists()
