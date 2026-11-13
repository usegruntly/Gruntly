"""Gemini CLI as a parent: the private folder with the system prompt and tool allowlist, key plumbing, parsing, and (when Gemini CLI is installed,
on PATH or named in GRUNTLY_TEST_GEMINI) the real binary against a stub that speaks the Gemini API and records what it sends."""
import json
import os
import shutil

import pytest

from gruntly import parents, probe
from gruntly.parents import base, gemini, prompts

REAL = os.environ.get("GRUNTLY_TEST_GEMINI") or shutil.which("gemini")
OUT = json.dumps({"session_id": "75780c07", "response": "ok", "stats": {"models": {"m": {
    "api": {"totalRequests": 2, "totalErrors": 0}, "tokens": {"input": 5, "prompt": 7, "candidates": 1, "total": 8, "cached": 2, "thoughts": 3, "tool": 0}}}}})


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("GRUNTLY_GEMINI_PARENT_HOME", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-SECRET-xyz")
    (tmp_path / "cfg").mkdir()
    monkeypatch.setattr(gemini, "which", lambda n: REAL or "/bin/gemini")
    return tmp_path


def test_the_delegating_command_writes_our_prompt_and_a_gruntly_only_tool_allowlist(cfg):
    c = gemini.GeminiParent().command("Fix add().", "delegating", None, "gemini")
    home = gemini.parent_home("delegating")
    a = c.argv
    assert a[1:] == ["--skip-trust", "--approval-mode", "yolo", "-o", "json", "-p", " "] and c.stdin == "Fix add()."
    assert c.files[str(home / "system.md")] == prompts.DELEGATING
    s = json.loads(c.files[str(home / ".gemini" / "settings.json")])
    assert s["tools"]["core"] == ["run_shell_command(gruntly)"] and s["security"]["auth"]["selectedType"] == "gemini-api-key"
    assert c.env["GEMINI_CLI_HOME"] == str(home) and c.env["GEMINI_SYSTEM_MD"] == str(home / "system.md") and len(c.notes) == 3
    assert c.env["GEMINI_API_KEY"] == "AIza-SECRET-xyz" and "AIza-SECRET-xyz" not in " ".join(a) and "AIza-SECRET-xyz" not in "".join(c.files.values())
    assert "-m" not in a and gemini.GeminiParent().command("t", "delegating", "gemini-x", "gemini").argv[-2:] == ["-m", "gemini-x"]


def test_the_working_command_is_gemini_as_shipped_in_yolo_mode(cfg):
    c = gemini.GeminiParent().command("Fix add().", "working")
    assert c.files == {} and "GEMINI_CLI_HOME" not in c.env and "GEMINI_SYSTEM_MD" not in c.env and c.env == {} and c.notes == []
    assert "yolo" in c.argv
    with pytest.raises(ValueError, match="mode must be one of"):
        gemini.GeminiParent().command("t", "lean")


def test_only_the_gemini_provider_fits_and_delegating_needs_it(cfg, monkeypatch):
    with pytest.raises(ValueError, match="speaks only the Gemini API.*not openai"):
        gemini.provider_setup("openai")
    with pytest.raises(ValueError, match="unknown provider 'nope'"):
        gemini.provider_setup("nope")
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(ValueError, match="no API key for gemini"):
        gemini.provider_setup("gemini")
    r = base.run(gemini.GeminiParent(), "t", "delegating")                      # no provider: its private folder has none of your own login
    assert r.returncode == 2 and r.outcome.is_error and "needs --provider gemini" in r.outcome.final_message


def test_the_json_output_is_read_for_the_reply_usage_and_session_and_an_error_is_an_error():
    out = gemini.GeminiParent().parse(OUT, "noise", 0)
    assert out.final_message == "ok" and not out.is_error and out.session_id == "75780c07" and out.turns == 2
    assert (out.usage.prompt, out.usage.completion, out.usage.cached, out.usage.reasoning) == (7, 1, 2, 3)
    bad = gemini.GeminiParent().parse(json.dumps({"session_id": "x", "error": {"type": "Error", "message": "Invalid auth method selected.", "code": 41}}), "", 41)
    assert bad.is_error and bad.final_message == "Invalid auth method selected."
    assert gemini.GeminiParent().parse("", "boom", 1).is_error and gemini.GeminiParent().parse("log line\n" + OUT, "", 0).final_message == "ok"


def test_gemini_is_registered_and_reports_its_limits_honestly():
    assert "gemini" in parents.names()
    c = parents.get_parent("gemini").capabilities()
    assert (c.replace_system_prompt, c.restrict_tools, c.restrict_shell, c.reports_usage, c.reports_cost) == (True, True, True, True, False)
    assert any("GEMINI.md" in n for n in c.notes) and any("Gemini API" in n for n in c.notes)


def _env(srv, tmp_path, extra=None):
    env = {"GOOGLE_GEMINI_BASE_URL": f"http://127.0.0.1:{srv.port}", "GRUNTLY_GEMINI_PARENT_HOME": str(tmp_path / "geminihome"), **(extra or {})}
    if os.name == "nt":                                                         # the .cmd shim needs chcp, the shell tool needs powershell
        root = os.environ.get("SystemRoot", r"C:\Windows")
        env["PATH"] = os.pathsep.join([os.environ["PATH"], os.path.join(root, "System32"), os.path.join(root, "System32", "WindowsPowerShell", "v1.0")])
    return env


@pytest.mark.skipif(not REAL, reason="Gemini CLI is not installed (set GRUNTLY_TEST_GEMINI to a gemini executable)")
def test_the_real_gemini_sends_exactly_our_prompt_and_only_a_shell_tool_and_the_key_reaches_it(cfg, tmp_path, monkeypatch):
    """No key, no cost. Measured on 0.68.0: about 30,400 characters of system prompt and eight tools by default; exactly our
    1,548 characters and one tool (`run_shell_command`) here."""
    with probe.StubServer() as srv:
        env = _env(srv, tmp_path)
        monkeypatch.setenv("GRUNTLY_GEMINI_PARENT_HOME", env["GRUNTLY_GEMINI_PARENT_HOME"])
        work = tmp_path / "work"
        work.mkdir()
        r = base.run(gemini.GeminiParent(), "Fix add().", "delegating", model="stub-model", provider="gemini", cwd=work, timeout_s=240, env=env)
        assert r.returncode == 0 and not r.outcome.is_error, (r.outcome.final_message, r.stderr[-300:])
        turn = srv.chat()[0]
        assert turn.tools == ["run_shell_command"] and turn.system.strip() == prompts.DELEGATING.strip()
        assert turn.auth == "AIza-SECRET-xyz" and "Fix add()." in turn.user and r.outcome.final_message == "ok"


@pytest.mark.skipif(not REAL, reason="Gemini CLI is not installed (set GRUNTLY_TEST_GEMINI to a gemini executable)")
@pytest.mark.parametrize("command,marker,runs", [("gruntly --help", None, True), ("echo hi > WRITE_MARKER.txt", "WRITE_MARKER.txt", False),
                                                  ("cat note.txt", None, False), ("gruntly --help && echo hi > CHAIN_MARKER.txt", "CHAIN_MARKER.txt", False)])
def test_the_real_gemini_runs_gruntly_and_denies_every_other_command(cfg, tmp_path, monkeypatch, command, marker, runs):
    """The stub plays a model that asks for one shell command. Measured: `gruntly` runs; a write, a read and a chained command come back
    `Tool execution denied by policy`."""
    fake = tmp_path / "fakebin"
    fake.mkdir()
    if os.name == "nt":
        (fake / "gruntly.cmd").write_text("@echo off\r\necho usage: gruntly fake\r\n", encoding="utf8")
    else:
        (fake / "gruntly").write_text("#!/bin/sh\necho usage: gruntly fake\n", encoding="utf8")
        (fake / "gruntly").chmod(0o755)
    script = [{"tool": "run_shell_command", "args": {"command": command}}, "done"]
    with probe.StubServer(script=script) as srv:
        env = _env(srv, tmp_path)
        env["PATH"] = str(fake) + os.pathsep + env.get("PATH", os.environ["PATH"])
        monkeypatch.setenv("GRUNTLY_GEMINI_PARENT_HOME", env["GRUNTLY_GEMINI_PARENT_HOME"])
        work = tmp_path / "work"
        work.mkdir()
        (work / "note.txt").write_text("SECRET_CONTENT", encoding="utf8")
        r = base.run(gemini.GeminiParent(), "do it", "delegating", model="stub-model", provider="gemini", cwd=work, timeout_s=240, env=env)
        assert r.returncode == 0 and r.outcome.final_message == "done"
        results = [x for s in srv.chat() for x in s.tool_results]
        assert results, "the harness never answered the tool call"
        if runs:
            assert "usage: gruntly fake" in results[0]
        else:
            assert "denied by policy" in results[0] and "SECRET_CONTENT" not in results[0]
        if marker:
            assert not (work / marker).exists()
