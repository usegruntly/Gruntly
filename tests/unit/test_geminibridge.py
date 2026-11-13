"""The Gemini-to-OpenAI bridge: the translation (against the shapes Gemini CLI really sends), the server, and, when Gemini CLI is installed (on PATH or named
in GRUNTLY_TEST_GEMINI), the real CLI doing a tool-using task through the bridge into a stub OpenAI-compatible server. No key, no cost."""
import json
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from gruntly import geminibridge as gb, probe
from gruntly.adapters import gemini as gchild
from gruntly.spec import Spec

REAL = os.environ.get("GRUNTLY_TEST_GEMINI") or shutil.which("gemini")

# What Gemini CLI 0.68.0 sent after the model asked to write a file (captured against the stub, trimmed).
BODY = {
    "systemInstruction": {"parts": [{"text": "You are a CLI agent."}]},
    "contents": [
        {"role": "user", "parts": [{"text": "<session_context>cwd</session_context>"}, {"text": "Create hello.txt containing hi there\n\n "}]},
        {"role": "model", "parts": [{"functionCall": {"id": "write_file_1_0", "name": "write_file", "args": {"file_path": "hello.txt", "content": "hi there"}},
                                      "thoughtSignature": "skip_thought_signature_validator"}]},
        {"role": "user", "parts": [{"functionResponse": {"id": "write_file_1_0", "name": "write_file", "response": {"output": "Successfully created hello.txt"}}}]}],
    "tools": [{"functionDeclarations": [
        {"name": "write_file", "description": "Writes content to a file.", "parametersJsonSchema": {"$schema": "x", "type": "object", "required": ["file_path", "content"],
                                                                                                 "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}}},
        {"name": "old_style", "description": "d", "parameters": {"type": "OBJECT", "properties": {"q": {"type": "STRING"}}}}]}],
    "generationConfig": {"temperature": 1, "topP": 0.95, "topK": 64, "thinkingConfig": {"includeThoughts": True}},
}


def test_the_conversation_becomes_system_user_assistant_with_tool_calls_and_tool_messages():
    msgs = gb.messages_to_openai(BODY)
    assert msgs[0] == {"role": "system", "content": "You are a CLI agent."}
    assert msgs[1] == {"role": "user", "content": "<session_context>cwd</session_context>\n\nCreate hello.txt containing hi there\n\n "}
    assert msgs[2]["role"] == "assistant" and msgs[2]["content"] is None
    assert msgs[2]["tool_calls"] == [{"id": "write_file_1_0", "type": "function",
                                       "function": {"name": "write_file", "arguments": json.dumps({"file_path": "hello.txt", "content": "hi there"})}}]
    assert msgs[3] == {"role": "tool", "tool_call_id": "write_file_1_0", "content": "Successfully created hello.txt"}      # a plain {output} is the string itself
    assert len(msgs) == 4


def test_a_response_without_an_id_answers_the_call_of_the_same_name_and_structured_responses_stay_json():
    body = {"contents": [{"role": "model", "parts": [{"functionCall": {"name": "ls", "args": {}}}, {"functionCall": {"name": "cat", "args": {"f": "a"}}}]},
                         {"role": "user", "parts": [{"functionResponse": {"name": "cat", "response": {"output": "x", "error": "e"}}},
                                                    {"functionResponse": {"name": "ls", "response": {"output": "a b"}}}]}]}
    msgs = gb.messages_to_openai(body)
    ids = {tc["function"]["name"]: tc["id"] for tc in msgs[0]["tool_calls"]}
    assert msgs[1] == {"role": "tool", "tool_call_id": ids["cat"], "content": json.dumps({"output": "x", "error": "e"})}
    assert msgs[2] == {"role": "tool", "tool_call_id": ids["ls"], "content": "a b"} and ids["ls"] != ids["cat"]


def test_tools_keep_their_schemas_with_dollar_schema_dropped_and_old_upper_case_types_lowered():
    t = gb.tools_to_openai(BODY["tools"])
    assert [x["function"]["name"] for x in t] == ["write_file", "old_style"] and t[0]["type"] == "function"
    assert t[0]["function"]["parameters"] == {"type": "object", "required": ["file_path", "content"], "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}}
    assert t[1]["function"]["parameters"] == {"type": "object", "properties": {"q": {"type": "string"}}}


def test_the_request_leaves_the_sampling_settings_to_the_server_and_asks_for_a_whole_answer():
    r = gb.request_to_openai(BODY, "m1")
    assert r["model"] == "m1" and r["stream"] is False and "temperature" not in r and "top_p" not in r and len(r["tools"]) == 2
    assert gb.request_to_openai({"contents": [], "generationConfig": {"maxOutputTokens": 100}}, "m")["max_tokens"] == 100


def test_an_openai_answer_becomes_text_and_function_call_parts_with_usage():
    resp = {"choices": [{"message": {"content": "ok", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "ls", "arguments": '{"d": "."}'}},
                                                                     {"id": "c2", "type": "function", "function": {"name": "bad", "arguments": "{not json"}}]}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "prompt_tokens_details": {"cached_tokens": 40}}}
    out = gb.response_from_openai(resp, "m1")
    c = out["candidates"][0]
    assert c["content"]["role"] == "model" and c["finishReason"] == "STOP"
    assert c["content"]["parts"] == [{"text": "ok"}, {"functionCall": {"id": "c1", "name": "ls", "args": {"d": "."}}}, {"functionCall": {"id": "c2", "name": "bad", "args": {}}}]
    assert out["usageMetadata"] == {"promptTokenCount": 100, "candidatesTokenCount": 20, "totalTokenCount": 120, "cachedContentTokenCount": 40}
    assert gb.response_from_openai({"choices": [{"message": {}, "finish_reason": "length"}]})["candidates"][0]["finishReason"] == "MAX_TOKENS"
    assert gb.response_from_openai({})["candidates"][0]["content"]["parts"] == [{"text": ""}]


def _post(url, body, expect_error=False):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_the_server_translates_both_ways_in_json_and_as_a_stream_and_sends_the_key_upstream():
    with probe.StubServer(script=[{"tool": "write_file", "args": {"file_path": "a.txt", "content": "x"}}]) as up:
        b = gb.start(up.base_url, "upstream-key")
        try:
            code, text = _post(f"{b.url}/v1beta/models/m1:generateContent", BODY)
            assert code == 200
            part = json.loads(text)["candidates"][0]["content"]["parts"][0]["functionCall"]
            assert part["name"] == "write_file" and part["args"] == {"file_path": "a.txt", "content": "x"} and part["id"] == "call_stub_1"
            seen = up.requests[0]
            assert seen.model == "m1" and seen.auth == "Bearer upstream-key" and seen.tools == ["write_file", "old_style"] and seen.system == "You are a CLI agent."
            assert seen.tool_results == ["Successfully created hello.txt"]
            code, text = _post(f"{b.url}/v1beta/models/m1:streamGenerateContent?alt=sse", BODY)
            assert text.startswith("data: ") and json.loads(text[6:].strip())["candidates"][0]["content"]["parts"][0]["text"] == "ok"
            code, text = _post(f"{b.url}/v1beta/models/m1:countTokens", BODY)
            assert code == 200 and json.loads(text)["totalTokens"] > 0
            assert _post(f"{b.url}/v1beta/models/m1:embedContent", BODY)[0] == 404 and _post(f"{b.url}/nonsense", {})[0] == 404
        finally:
            stats = b.stop()
    assert stats["requests"] == 4 and stats["tool_calls"] == 1 and stats["errors"] == 0


def test_an_upstream_error_comes_back_in_the_gemini_error_shape_with_the_same_code_and_an_unreachable_one_is_503():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            data = b'{"error": "slow down"}'
            self.send_response(429)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    b = gb.start(f"http://127.0.0.1:{srv.server_address[1]}/v1", "k")
    try:
        code, text = _post(f"{b.url}/v1beta/models/m:generateContent", BODY)
        assert code == 429 and json.loads(text)["error"] == {"code": 429, "message": '{"error": "slow down"}', "status": "RESOURCE_EXHAUSTED"}
    finally:
        srv.shutdown()
        srv.server_close()
        b.stop()
    dead = gb.start("http://127.0.0.1:9/v1", "k", timeout=3)
    try:
        code, text = _post(f"{dead.url}/v1beta/models/m:generateContent", BODY)
        assert code == 503 and json.loads(text)["error"]["status"] == "UNAVAILABLE"
    finally:
        assert dead.stop()["errors"] == 1


def test_the_child_adapter_points_gemini_at_the_bridge_with_a_private_home_and_the_parents_approval_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(gchild, "which", lambda n: "/bin/gemini")
    wt = tmp_path / "runs" / "r1" / "wt"
    t = Spec(brief="b", endpoint="http://127.0.0.1:1234/v1", api_key="local", model="qwen-9b")
    with pytest.raises(RuntimeError, match="needs the bridge"):
        gchild.GeminiAdapter().command(t, wt, "p", None)
    t._bridge_url = "http://127.0.0.1:5555"
    monkeypatch.setenv("GRUNTLY_PARENT_MODE", "acceptEdits")
    c = gchild.GeminiAdapter().command(t, wt, "Fix add().", None)
    assert c.argv[1:] == ["-m", "qwen-9b", "--skip-trust", "--approval-mode", "auto_edit", "-o", "json", "-p", " "] and c.stdin == "Fix add()."
    assert c.env["GOOGLE_GEMINI_BASE_URL"] == "http://127.0.0.1:5555" and c.env["GEMINI_API_KEY"] == "gruntly-bridge" and c.env["GEMINI_CLI_HOME"].endswith("gemini-home")
    assert json.loads((Path(c.env["GEMINI_CLI_HOME"]) / ".gemini" / "settings.json").read_text())["security"]["auth"]["selectedType"] == "gemini-api-key"
    monkeypatch.setenv("GRUNTLY_PARENT_MODE", "plan")
    argv = gchild.GeminiAdapter().command(t, wt, "x", None).argv
    assert argv[argv.index("--approval-mode") + 1] == "plan"


def test_the_json_output_is_read_for_the_reply_session_usage_and_an_error():
    out = json.dumps({"session_id": "s1", "response": "done", "stats": {"models": {"m": {"api": {"totalRequests": 3}, "tokens": {"prompt": 300, "candidates": 30, "cached": 10}}}}})
    o = gchild.GeminiAdapter().parse("log\n" + out, "", 0)
    assert o.final_message == "done" and not o.is_error and o.session_id == "s1"
    assert o.usage == {"available": True, "input_tokens": 300, "output_tokens": 30, "total_tokens": 330, "requests": 3, "input_per_request": 100}
    assert gchild.GeminiAdapter().parse(json.dumps({"error": {"message": "Invalid auth method selected."}}), "", 41).is_error
    assert gchild.GeminiAdapter().parse("", "boom", 1).is_error and gchild.GeminiAdapter().capabilities().resume is False


def _repo(path):
    path.mkdir(parents=True)
    (path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q"], ["git", "add", "."], ["git", "commit", "-qm", "init"]):
        subprocess.run(cmd, cwd=path, env=env, check=True, capture_output=True)


def _path_with_windows_dirs():
    if os.name != "nt":
        return os.environ["PATH"]
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.pathsep.join([os.environ["PATH"], os.path.join(root, "System32"), os.path.join(root, "System32", "WindowsPowerShell", "v1.0")])


@pytest.mark.skipif(not REAL, reason="Gemini CLI is not installed (set GRUNTLY_TEST_GEMINI to a gemini executable)")
def test_the_real_gemini_cli_edits_a_file_through_the_bridge_and_the_model_server_sees_the_whole_exchange(tmp_path, monkeypatch):
    """The stub plays a model that calls write_file and then answers. The real CLI sends Gemini requests; the bridge turns them into chat completions for the
    stub; the CLI executes the tool and sends its result back, which the stub receives as a tool message. Measured on 0.68.0."""
    monkeypatch.setattr(gchild, "which", lambda n: REAL)
    monkeypatch.setenv("GRUNTLY_PARENT_MODE", "bypassPermissions")
    fixed = "def add(a, b):\n    return a + b\n"
    with probe.StubServer(script=[{"tool": "write_file", "args": {"file_path": "calc.py", "content": fixed}}, "fixed add"]) as up:
        work = tmp_path / "runs" / "r1" / "wt"
        _repo(work)
        b = gb.start(up.base_url, "local")
        try:
            t = Spec(brief="b", endpoint=up.base_url, api_key="local", model="m1")
            t._bridge_url = b.url
            cmd = gchild.GeminiAdapter().command(t, work, "Fix add() in calc.py", None)
            env = {**os.environ, **cmd.env, "PATH": _path_with_windows_dirs()}
            p = subprocess.Popen(cmd.argv, cwd=str(work), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf8", errors="replace")
            out, err = p.communicate(cmd.stdin, timeout=240)
        finally:
            b.stop()
        o = gchild.GeminiAdapter().parse(out, err, p.returncode)
        assert not o.is_error and o.final_message == "fixed add", (out[-400:], err[-400:])
        assert (work / "calc.py").read_text(encoding="utf8") == fixed
        first, second = up.chat()[0], up.chat()[1]
        assert first.model == "m1" and "write_file" in first.tools and first.auth == "Bearer local" and "Fix add() in calc.py" in first.user
        assert len(first.system) > 5000                                      # Gemini CLI's own prompt, as shipped
        assert second.tool_results and "calc.py" in second.tool_results[0]
        assert o.usage["available"] and o.usage["requests"] == 2
