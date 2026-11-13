"""Codex CLI and Aider as children: the command lines, the environment, parsing, and (when the harness is installed, on PATH or named in
GRUNTLY_TEST_CODEX / GRUNTLY_TEST_AIDER) the real binary against a stub model server that records what it sends."""
import json
import os
import shutil
import subprocess

import pytest

from gruntly import probe
from gruntly.adapters import aider, base, codex
from gruntly.spec import Spec

REAL_CODEX = os.environ.get("GRUNTLY_TEST_CODEX") or shutil.which("codex")
REAL_AIDER = os.environ.get("GRUNTLY_TEST_AIDER") or shutil.which("aider")
EVENTS = "\n".join(json.dumps(e) for e in [
    {"type": "thread.started", "thread_id": "01a1"},
    {"type": "item.completed", "item": {"id": "item_0", "type": "error", "message": "Model metadata for `m` not found."}},
    {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "done"}},
    {"type": "turn.completed", "usage": {"input_tokens": 70, "cached_input_tokens": 20, "output_tokens": 10}},
    {"type": "turn.completed", "usage": {"input_tokens": 30, "cached_input_tokens": 0, "output_tokens": 5}}])


def _task(endpoint="http://127.0.0.1:1234/v1", **kw):
    return Spec(brief="b", endpoint=endpoint, api_key="proxy-dummy", model="m1", **kw)


@pytest.fixture
def wt(tmp_path):
    return tmp_path / "runs" / "r1" / "wt"


def test_the_codex_child_is_a_responses_provider_with_the_key_in_the_environment_and_its_own_home(wt, monkeypatch):
    monkeypatch.setattr(codex, "which", lambda n: "/bin/codex")
    monkeypatch.setenv("GRUNTLY_PARENT_MODE", "bypassPermissions")
    c = codex.CodexAdapter().command(_task(), wt, "Fix add().", None)
    a = c.argv
    assert a[:4] == ["/bin/codex", "exec", "--skip-git-repo-check", "--json"] and a[-1] == "-" and c.stdin == "Fix add()." and "--ephemeral" in a
    prov = [x for x in a if x.startswith("model_providers.gruntly=")][0]
    assert 'wire_api = "responses"' in prov and 'base_url = "http://127.0.0.1:1234/v1"' in prov and 'env_key = "GRUNTLY_CHILD_API_KEY"' in prov
    assert c.env["GRUNTLY_CHILD_API_KEY"] == "proxy-dummy" and "proxy-dummy" not in " ".join(a)
    assert c.env["CODEX_HOME"].endswith(os.path.join("child-state", "wt", "codex-home")) and a[a.index("-m") + 1] == "m1" and a[a.index("-C") + 1] == str(wt)
    assert "--dangerously-bypass-approvals-and-sandbox" in a
    monkeypatch.setenv("GRUNTLY_PARENT_MODE", "acceptEdits")
    b = codex.CodexAdapter().command(_task(), wt, "x", None).argv
    assert b[b.index("-s") + 1] == "workspace-write" and "--dangerously-bypass-approvals-and-sandbox" not in b
    monkeypatch.setenv("GRUNTLY_PARENT_MODE", "plan")
    assert codex.CodexAdapter().command(_task(), wt, "x", None).argv[-5:-3] == ["-s", "read-only"]


def test_the_codex_events_are_read_for_the_reply_session_and_usage_and_a_warning_is_not_a_failure():
    out = codex.CodexAdapter().parse(EVENTS, "", 0)
    assert out.final_message == "done" and not out.is_error and out.session_id == "01a1"
    assert out.usage == {"available": True, "input_tokens": 100, "output_tokens": 15, "total_tokens": 115, "requests": 2, "input_per_request": 50}
    bad = codex.CodexAdapter().parse(json.dumps({"type": "turn.failed", "error": {"message": "quota"}}), "", 1)
    assert bad.is_error and bad.final_message == "quota"
    assert codex.CodexAdapter().parse("", "boom", 1).is_error and codex.CodexAdapter().capabilities().resume is False


def test_the_aider_child_keeps_everything_it_would_write_out_of_the_tree(wt, monkeypatch):
    monkeypatch.setattr(aider, "which", lambda n: "/bin/aider")
    c = aider.AiderAdapter().command(_task(), wt, "Fix add().", None)
    a = c.argv
    state = wt.parents[1] / "child-state" / "wt" / "aider"
    assert a[a.index("--model") + 1] == "openai/m1" and a[a.index("--message") + 1] == "Fix add()." and c.stdin is None
    for f in ("--yes-always", "--no-auto-commits", "--no-gitignore", "--no-pretty", "--no-stream", "--no-check-update", "--no-analytics"):
        assert f in a
    assert a[a.index("--map-tokens") + 1] == "0" and a[a.index("--chat-history-file") + 1] == str(state / "chat.md") and state.is_dir()
    assert c.env["OPENAI_API_BASE"] == "http://127.0.0.1:1234/v1" and c.env["OPENAI_API_KEY"] == "proxy-dummy" and "--chat-mode" not in a
    monkeypatch.setenv("GRUNTLY_PARENT_MODE", "plan")
    assert aider.AiderAdapter().command(_task(), wt, "x", None).argv[-2:] == ["--chat-mode", "ask"]


def test_the_aider_output_is_read_for_the_reply_and_the_token_lines():
    out = aider.AiderAdapter().parse("Aider v0.86.2\nMain model: x\nI changed add().\n\nTokens: 1.2k sent, 45 received.\nTokens: 300 sent, 5 received.\n", "", 0)
    assert out.final_message == "I changed add()." and not out.is_error
    assert out.usage == {"available": True, "input_tokens": 1500, "output_tokens": 50, "total_tokens": 1550, "requests": 2, "input_per_request": 750}
    assert aider.AiderAdapter().parse("", "boom", 1).is_error and aider.AiderAdapter().parse("Aider v1\n", "", 0).is_error


def _repo(path):
    path.mkdir(parents=True)
    (path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q"], ["git", "add", "."], ["git", "commit", "-qm", "init"]):
        subprocess.run(cmd, cwd=path, env=env, check=True, capture_output=True)


def _run(adapter, cmd, work, timeout=240):
    env = {**os.environ, **cmd.env}
    p = subprocess.Popen(cmd.argv, cwd=str(work), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf8", errors="replace")
    try:
        out, err = p.communicate(cmd.stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        adapter.cancel(p)
        raise
    return adapter.parse(out, err, p.returncode), out, err


@pytest.mark.skipif(not REAL_CODEX, reason="Codex is not installed (set GRUNTLY_TEST_CODEX to a codex executable)")
def test_the_real_codex_child_talks_to_the_endpoint_with_the_key_and_the_task(tmp_path, monkeypatch):
    monkeypatch.setattr(codex, "which", lambda n: REAL_CODEX)
    monkeypatch.setenv("GRUNTLY_PARENT_MODE", "acceptEdits")
    with probe.StubServer() as srv:
        work = tmp_path / "runs" / "r1" / "wt"
        _repo(work)
        cmd = codex.CodexAdapter().command(_task(srv.base_url), work, "Fix add().", None)
        cmd.env["GRUNTLY_CHILD_API_KEY"] = "dummy-key-123"
        out, so, se = _run(codex.CodexAdapter(), cmd, work)
        assert not out.is_error and out.final_message == "ok", (so[-300:], se[-300:])
        turn = srv.chat()[0]
        assert turn.model == "m1" and turn.auth == "Bearer dummy-key-123" and "Fix add()." in turn.user and "exec_command" in turn.tools
        assert out.usage["available"] and out.usage["requests"] >= 1


@pytest.mark.skipif(not REAL_AIDER, reason="Aider is not installed (set GRUNTLY_TEST_AIDER to an aider executable)")
def test_the_real_aider_child_leaves_the_tree_exactly_as_it_found_it_when_the_model_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(aider, "which", lambda n: REAL_AIDER)
    with probe.StubServer(reply="ok") as srv:
        work = tmp_path / "runs" / "r1" / "wt"
        _repo(work)
        home = tmp_path / "home"
        home.mkdir()
        cmd = aider.AiderAdapter().command(_task(srv.base_url), work, "Fix add().", None)
        cmd.env["OPENAI_API_KEY"] = "dummy-key-123"
        cmd.env.update({"HOME": str(home), "USERPROFILE": str(home)})
        out, so, se = _run(aider.AiderAdapter(), cmd, work)
        assert not out.is_error and "ok" in out.final_message, (so[-300:], se[-300:])
        turn = srv.chat()[0]
        assert turn.model in ("m1", "openai/m1") and turn.auth == "Bearer dummy-key-123" and "Fix add()." in turn.user
        status = subprocess.run(["git", "status", "--porcelain"], cwd=work, capture_output=True, text=True).stdout
        assert status.strip() == "", f"Aider left files in the tree: {status}"            # no .aider* history, no tags cache, no .gitignore edit
