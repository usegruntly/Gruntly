"""Aider as a parent (working mode only): the command line, the message file, key plumbing, parsing, why delegating is refused, and (when Aider is
installed, on PATH or named in GRUNTLY_TEST_AIDER) the real binary against a stub model server that records what it sends."""
import os
import shutil

import pytest

from gruntly import parents, probe, providers
from gruntly.parents import aider, base

REAL = os.environ.get("GRUNTLY_TEST_AIDER") or shutil.which("aider")
SAMPLE = "Aider v0.86.2\nMain model: openai/stub-model with whole edit format\nGit repo: .git with 0 files\nRepo-map: disabled\nok\n\nTokens: 1.2k sent, 45 received.\n"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "cfg").mkdir()
    monkeypatch.setattr(aider, "which", lambda n: REAL or "/bin/aider")
    return tmp_path


def test_delegating_is_refused_with_the_reason_and_what_to_do_instead(cfg):
    with pytest.raises(ValueError, match=r"cannot be a delegating parent.*--mode working.*child"):
        aider.AiderParent().command("t", "delegating")
    r = base.run(aider.AiderParent(), "t", "delegating")
    assert r.returncode == 2 and r.outcome.is_error and "no tool loop" in r.outcome.final_message


def test_the_working_command_gives_the_task_in_a_file_and_keeps_aider_quiet_and_unattended(cfg, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SECRET-xyz")
    c = aider.AiderParent().command("Fix add().", "working", "meta/llama", "openrouter")
    msg = str(cfg / "state" / "aider-parent" / "message.txt")
    assert c.files == {msg: "Fix add()."} and c.stdin is None and len(c.notes) == 1 and ".gitignore" in c.notes[0]
    a = c.argv
    assert a[a.index("--message-file") + 1] == msg and a[a.index("--model") + 1] == "openai/meta/llama"
    for f in ("--yes-always", "--no-auto-commits", "--no-check-update", "--no-analytics", "--no-pretty", "--no-stream", "--no-fancy-input"):
        assert f in a
    assert c.env["OPENAI_API_BASE"] == "https://openrouter.ai/api/v1" and c.env["OPENAI_API_KEY"] == "sk-or-SECRET-xyz"
    assert "sk-or-SECRET-xyz" not in " ".join(a) and "sk-or-SECRET-xyz" not in "".join(c.files.values())
    assert "--model" not in aider.AiderParent().command("t", "working").argv


def test_a_local_server_needs_no_key_and_a_provider_that_cannot_be_used_is_a_clear_error(cfg, monkeypatch):
    flags, env = aider.provider_setup("ollama", "qwen3:8b")
    assert flags == ["--model", "openai/qwen3:8b"] and env["OPENAI_API_KEY"] == "local"
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    with pytest.raises(ValueError, match="no API key for openrouter"):
        aider.provider_setup("openrouter", "m")
    with pytest.raises(ValueError, match="provider groq has no default model"):
        aider.provider_setup("groq", None)
    with pytest.raises(ValueError, match="unknown provider 'nope'"):
        aider.provider_setup("nope", "m")


def test_the_output_is_read_for_the_reply_and_the_token_line():
    out = aider.AiderParent().parse(SAMPLE, "", 0)
    assert out.final_message == "ok" and not out.is_error and (out.usage.prompt, out.usage.completion) == (1200, 45)
    assert aider.AiderParent().parse("", "boom", 1).is_error and aider.AiderParent().parse("", "", 0).final_message == "no output"


def test_aider_is_registered_as_working_only_and_is_never_picked_as_a_delegating_parent(monkeypatch):
    assert "aider" in parents.names()
    c = parents.get_parent("aider").capabilities()
    assert c.modes == ("working",) and not c.replace_system_prompt and not c.restrict_tools and not c.restrict_shell and c.reports_usage
    monkeypatch.setattr(parents, "table", lambda: {"aider": aider.AiderParent})
    monkeypatch.setattr(aider.AiderParent, "detect", lambda self: base.Detection(True, "0.86.2"))
    assert parents.pick_installed() is None and parents.pick_installed("working") == "aider"


@pytest.mark.skipif(not REAL, reason="Aider is not installed (set GRUNTLY_TEST_AIDER to an aider executable)")
def test_the_real_aider_sends_the_task_to_the_named_model_with_the_key_and_reports_tokens(cfg, tmp_path, monkeypatch):
    """No key, no cost. Measured on 0.86.2: Aider's own prompt carries the task from the message file; the key arrives as a bearer token."""
    with probe.StubServer(reply="ok") as srv:
        monkeypatch.setitem(providers.ALL, "stubprov", providers.Provider(name="stubprov", base_url=srv.base_url, key_env="STUB_API_KEY", default_model="stub-model"))
        monkeypatch.setenv("STUB_API_KEY", "dummy-key-123")
        work = tmp_path / "work"
        work.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        r = base.run(aider.AiderParent(), "Fix add().", "working", provider="stubprov", cwd=work, timeout_s=240,
                     env={"HOME": str(home), "USERPROFILE": str(home), "PYTHONUTF8": "1"})
        assert r.returncode == 0 and not r.outcome.is_error, (r.outcome.final_message, r.stderr[-300:])
        turn = srv.chat()[0]
        assert turn.model == "openai/stub-model" or turn.model == "stub-model"
        assert turn.auth == "Bearer dummy-key-123" and "Fix add()." in turn.user and "ok" in r.outcome.final_message
