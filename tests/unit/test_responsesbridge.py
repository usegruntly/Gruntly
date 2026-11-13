"""The Responses-to-chat bridge: the translation (against the shapes Codex really sends), the server, the wrapper, and, when Codex is installed (on PATH or named in
GRUNTLY_TEST_CODEX), the real CLI doing a tool-using task through the bridge into a stub chat-completions server. No key, no cost."""
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from gruntly import probe, responsesbridge as rb
from gruntly.adapters import codex as cchild
from gruntly.spec import Spec

REAL = os.environ.get("GRUNTLY_TEST_CODEX") or shutil.which("codex")

# What Codex 0.167.2 sent on its second request of a tool exchange (trimmed), plus a custom tool and a reasoning item.
BODY = {
    "model": "m1", "stream": True, "tool_choice": "auto", "parallel_tool_calls": True, "store": False, "include": ["reasoning.encrypted_content"],
    "input": [
        {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "You direct a local agent."}]},
        {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "<environment>cwd</environment>"}]},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "run echo hello"}]},
        {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "xxx"},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Running it."}]},
        {"type": "function_call", "status": "completed", "id": "fc_1", "name": "exec_command", "arguments": "{\"cmd\": \"echo hello\"}", "call_id": "call_1"},
        {"type": "function_call", "status": "completed", "id": "fc_2", "name": "exec_command", "arguments": "{\"cmd\": \"pwd\"}", "call_id": "call_2"},
        {"type": "function_call_output", "id": "fco_1", "call_id": "call_1", "output": "hello"},
        {"type": "function_call_output", "id": "fco_2", "call_id": "call_2", "output": [{"type": "input_text", "text": "/work"}]},
        {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "late developer note"}]}],
    "tools": [{"type": "function", "name": "exec_command", "description": "Runs a command.", "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}},
              {"type": "namespace", "name": "multi_agent_v1", "tools": []}, {"type": "web_search"},
              {"type": "custom", "name": "apply_patch", "description": "Edit files.", "format": {"type": "grammar"}}]}


def test_the_conversation_becomes_one_system_message_user_assistant_with_calls_and_tool_messages():
    m = rb.input_to_messages(BODY)
    assert m[0] == {"role": "system", "content": "You direct a local agent.\n\n<environment>cwd</environment>"}
    assert m[1] == {"role": "user", "content": "run echo hello"}
    assert m[2]["role"] == "assistant" and m[2]["content"] == "Running it." and [c["id"] for c in m[2]["tool_calls"]] == ["call_1", "call_2"]
    assert m[2]["tool_calls"][0]["function"] == {"name": "exec_command", "arguments": "{\"cmd\": \"echo hello\"}"}
    assert m[3] == {"role": "tool", "tool_call_id": "call_1", "content": "hello"} and m[4] == {"role": "tool", "tool_call_id": "call_2", "content": "/work"}
    assert m[5] == {"role": "user", "content": "late developer note"}               # a developer message after the start would break templates that want system first
    assert len(m) == 6                                                               # the reasoning item is skipped


def test_instructions_come_first_and_a_plain_string_input_is_a_user_message():
    m = rb.input_to_messages({"instructions": "Be brief.", "input": "hi"})
    assert m == [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}]


def test_function_tools_pass_a_custom_tool_becomes_a_one_string_function_and_hosted_and_namespace_tools_are_dropped():
    t = rb.tools_to_openai(BODY["tools"])
    assert [x["function"]["name"] for x in t] == ["exec_command", "apply_patch"]
    assert t[0]["function"]["parameters"]["required"] == ["cmd"]
    assert t[1]["function"]["parameters"] == {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]}
    r = rb.request_to_openai({**BODY, "parallel_tool_calls": False, "max_output_tokens": 50})
    assert r["model"] == "m1" and r["stream"] is False and r["parallel_tool_calls"] is False and r["max_tokens"] == 50 and "store" not in r and len(r["tools"]) == 2


def test_a_chat_answer_becomes_message_and_call_items_with_usage_and_custom_calls_come_back_as_custom():
    resp = {"choices": [{"message": {"content": "On it.", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "exec_command", "arguments": "{\"cmd\": \"ls\"}"}},
                                                                         {"id": "c2", "type": "function", "function": {"name": "apply_patch", "arguments": "{\"input\": \"*** Begin Patch\"}"}}]}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "prompt_tokens_details": {"cached_tokens": 40}, "completion_tokens_details": {"reasoning_tokens": 5}}}
    items, usage = rb.response_items(resp, {"apply_patch"})
    assert [i["type"] for i in items] == ["message", "function_call", "custom_tool_call"]
    assert items[0]["content"][0]["text"] == "On it." and items[1]["call_id"] == "c1" and items[1]["arguments"] == "{\"cmd\": \"ls\"}"
    assert items[2]["input"] == "*** Begin Patch" and items[2]["call_id"] == "c2"
    assert usage == {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120, "input_tokens_details": {"cached_tokens": 40}, "output_tokens_details": {"reasoning_tokens": 5}}
    assert rb.response_items({})[0] == []


def test_the_stream_has_created_item_events_and_completed_with_the_whole_response():
    items, usage = rb.response_items({"choices": [{"message": {"content": "hi", "tool_calls": [{"id": "c1", "function": {"name": "f", "arguments": "{}"}}]}}]})
    names = [n for n, _ in rb.events(items, usage, "m1")]
    assert names == ["response.created", "response.output_item.added", "response.output_text.delta", "response.output_text.done", "response.output_item.done",
                     "response.output_item.added", "response.output_item.done", "response.completed"]
    last = rb.events(items, usage, "m1")[-1][1]
    assert last["response"]["status"] == "completed" and last["response"]["output"] == items and last["response"]["usage"] == usage


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _sse(text):
    return [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ")]


def test_the_server_translates_both_ways_sends_the_key_upstream_and_refuses_other_paths():
    with probe.StubServer(script=[{"tool": "exec_command", "args": {"cmd": "echo hi"}}]) as up:
        b = rb.start(up.base_url, "upstream-key")
        try:
            code, text = _post(f"{b.url}/responses", BODY)
            assert code == 200
            ev = _sse(text)
            done = [e for e in ev if e["type"] == "response.output_item.done"]
            assert done[0]["item"]["type"] == "function_call" and json.loads(done[0]["item"]["arguments"]) == {"cmd": "echo hi"} and done[0]["item"]["call_id"] == "call_stub_1"
            assert ev[-1]["type"] == "response.completed" and ev[-1]["response"]["usage"]["input_tokens"] == 7
            seen = up.requests[0]
            assert seen.model == "m1" and seen.auth == "Bearer upstream-key" and seen.tools == ["exec_command", "apply_patch"] and seen.system.startswith("You direct a local agent.")
            assert seen.tool_results == ["hello", "/work"]
            assert _post(f"{b.url}/chat/completions", {})[0] == 404 and _post(f"{b.url}/other", {})[0] == 404
            with urllib.request.urlopen(f"{b.url}/models", timeout=10) as r:                      # the model list is passed through
                assert json.loads(r.read())["data"][0]["id"] == "stub-model"
        finally:
            stats = b.stop()
    assert stats["requests"] == 1 and stats["tool_calls"] == 1 and stats["errors"] == 0


def test_an_upstream_error_keeps_its_code_and_an_unreachable_upstream_is_503():
    dead = rb.start("http://127.0.0.1:9/v1", "k", timeout=3)
    try:
        code, text = _post(f"{dead.url}/responses", BODY)
        assert code == 503 and json.loads(text)["error"]["type"] == "server_error"
    finally:
        assert dead.stop()["errors"] == 1


def test_the_wrapper_fills_in_the_bridge_url_runs_the_command_and_returns_its_code(capfd, monkeypatch):
    with probe.StubServer() as up:
        code = rb.main(["--upstream", up.base_url, "--", sys.executable, "-c", "import sys, urllib.request; u = sys.argv[1]; print(u); "
                        "sys.exit(0 if urllib.request.urlopen(u + '/models').status == 200 else 3)", "{bridge_url}"])
    assert code == 0 and capfd.readouterr().out.strip().startswith("http://127.0.0.1:") and rb.main(["--upstream", "http://x/v1", "--", sys.executable, "-c", "raise SystemExit(7)"]) == 7
    monkeypatch.delenv("NO_SUCH_KEY_VAR", raising=False)
    assert rb.main(["--upstream", "http://x/v1", "--key-env", "NO_SUCH_KEY_VAR", "--", sys.executable, "-c", "pass"]) == 2
    assert rb.main(["--upstream", "http://x/v1", "--"]) == 2 and rb.main(["--upstream", "http://x/v1", "--", "no-such-program-xyz"]) == 127


def _repo(path):
    path.mkdir(parents=True)
    (path / "a.txt").write_text("x\n", encoding="utf8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q"], ["git", "add", "."], ["git", "commit", "-qm", "init"]):
        subprocess.run(cmd, cwd=path, env=env, check=True, capture_output=True)


@pytest.mark.skipif(not REAL, reason="Codex is not installed (set GRUNTLY_TEST_CODEX to a codex executable)")
def test_the_real_codex_runs_a_command_through_the_bridge_and_the_chat_server_sees_the_whole_exchange(tmp_path, monkeypatch):
    """The stub plays a chat model that calls exec_command and then answers. The real Codex sends Responses requests; the bridge turns them into chat
    completions; Codex runs the command and sends its result back, which the stub receives as a tool message. Measured on 0.167.2."""
    monkeypatch.setattr(cchild, "which", lambda n: REAL)
    monkeypatch.setenv("GRUNTLY_PARENT_MODE", "bypassPermissions")
    with probe.StubServer(script=[{"tool": "exec_command", "args": {"cmd": "git --version > ver.txt"}}, "wrote it"]) as up:
        work = tmp_path / "runs" / "r1" / "wt"
        _repo(work)
        b = rb.start(up.base_url, "local")
        try:
            t = Spec(brief="b", endpoint=b.url, api_key="local", model="m1")
            cmd = cchild.CodexAdapter().command(t, work, "Record the git version in ver.txt", None)
            p = subprocess.Popen(cmd.argv, cwd=str(work), env={**os.environ, **cmd.env}, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 encoding="utf8", errors="replace")
            out, err = p.communicate(cmd.stdin, timeout=240)
        finally:
            b.stop()
        o = cchild.CodexAdapter().parse(out, err, p.returncode)
        assert not o.is_error and o.final_message == "wrote it", (out[-400:], err[-400:])
        raw = (work / "ver.txt").read_bytes()                                       # Windows PowerShell writes a `>` redirect as UTF-16
        assert "git version" in (raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf8", "replace"))
        first, second = up.chat()[0], up.chat()[1]
        assert first.model == "m1" and "exec_command" in first.tools and "web_search" not in first.tools and first.auth == "Bearer local"
        assert "Record the git version" in first.user and second.tool_results and o.usage["available"]


def test_a_providers_extra_content_on_a_tool_call_is_remembered_by_call_id_and_put_back_when_the_call_is_echoed():
    """Gemini 3 (through its OpenAI-compatible endpoint) attaches a thought_signature to a tool call and rejects the next request unless it comes back."""
    extras = {}
    resp = {"choices": [{"message": {"content": None, "tool_calls": [{"id": "c1", "type": "function", "extra_content": {"google": {"thought_signature": "SIG1"}},
                                                                     "function": {"name": "exec_command", "arguments": "{}"}},
                                                                    {"id": "c2", "type": "function", "function": {"name": "exec_command", "arguments": "{}"}}]}}]}
    rb.response_items(resp, None, extras)
    assert extras == {"c1": {"google": {"thought_signature": "SIG1"}}}
    body = {"input": [{"type": "message", "role": "user", "content": "go"},
                      {"type": "function_call", "name": "exec_command", "arguments": "{}", "call_id": "c1"}, {"type": "function_call", "name": "exec_command", "arguments": "{}", "call_id": "c2"},
                      {"type": "function_call_output", "call_id": "c1", "output": "a"}, {"type": "function_call_output", "call_id": "c2", "output": "b"}]}
    calls = rb.input_to_messages(body, extras)[1]["tool_calls"]
    assert calls[0]["extra_content"] == {"google": {"thought_signature": "SIG1"}} and "extra_content" not in calls[1]
    assert "extra_content" not in rb.input_to_messages(body)[1]["tool_calls"][0]                  # no memory, nothing invented


def test_the_server_keeps_the_signature_between_two_requests():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    first = {"choices": [{"message": {"content": None, "tool_calls": [{"id": "c9", "type": "function", "extra_content": {"google": {"thought_signature": "S9"}},
                                                                      "function": {"name": "exec_command", "arguments": "{\"cmd\": \"x\"}"}}]}, "finish_reason": "tool_calls"}],
             "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    seen = []

    class Up(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0))))
            data = json.dumps(first if len(seen) == 1 else {"choices": [{"message": {"content": "ok"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    from http.server import HTTPServer as _H
    srv = _H(("127.0.0.1", 0), Up)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    b = rb.start(f"http://127.0.0.1:{srv.server_address[1]}/v1", "k")
    try:
        _post(f"{b.url}/responses", {"model": "m", "input": [{"type": "message", "role": "user", "content": "go"}], "tools": BODY["tools"][:1]})
        _post(f"{b.url}/responses", {"model": "m", "tools": BODY["tools"][:1], "input": [{"type": "message", "role": "user", "content": "go"},
                                                                                         {"type": "function_call", "name": "exec_command", "arguments": "{}", "call_id": "c9"},
                                                                                         {"type": "function_call_output", "call_id": "c9", "output": "r"}]})
    finally:
        b.stop()
        srv.shutdown()
        srv.server_close()
    assert seen[1]["messages"][1]["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "S9"}}
