"""The proxy remembers a provider's `extra_content` on tool calls (Gemini 3's thought_signature) and restores it when a harness echoes the call without it."""
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from gruntly import proxy

SIG = {"google": {"thought_signature": "SIG-A"}}


def body(messages):
    return json.dumps({"model": "m", "messages": messages}).encode()


ECHOED = [{"role": "user", "content": "go"}, {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}},
                                                                                                   {"id": "c2", "type": "function", "function": {"name": "f", "arguments": "{}"}}]},
          {"role": "tool", "tool_call_id": "c1", "content": "r"}]


def test_a_plain_json_response_teaches_it_and_a_later_request_gets_it_back_on_that_call_only():
    ex = proxy.ToolCallExtras()
    assert ex.restore(body(ECHOED)) == body(ECHOED)                               # nothing learned yet: the body is untouched, byte for byte
    tap = ex.tap()
    tap.feed(json.dumps({"choices": [{"message": {"tool_calls": [{"id": "c1", "type": "function", "extra_content": SIG, "function": {"name": "f", "arguments": "{}"}}]}}]}).encode())
    tap.finish()
    out = json.loads(ex.restore(body(ECHOED)))
    calls = out["messages"][1]["tool_calls"]
    assert calls[0]["extra_content"] == SIG and "extra_content" not in calls[1]
    already = json.loads(ex.restore(body([{"role": "assistant", "tool_calls": [{"id": "c1", "extra_content": {"mine": 1}}]}])))
    assert already["messages"][0]["tool_calls"][0]["extra_content"] == {"mine": 1}      # a harness that did echo it is not overridden


def test_a_streamed_response_teaches_it_even_when_the_signature_comes_in_a_later_chunk_of_the_same_call():
    ex = proxy.ToolCallExtras()
    chunks = [{"choices": [{"delta": {"role": "assistant", "tool_calls": [{"index": 0, "id": "cs1", "type": "function", "function": {"name": "f", "arguments": ""}}]}}]},
              {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{}"}, "extra_content": SIG}]}}]},
              {"choices": [{"delta": {}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}]
    sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    tap = ex.tap()
    for i in range(0, len(sse), 40):                                               # in small pieces, as a network delivers it
        tap.feed(sse[i:i + 40].encode())
    tap.finish()
    assert ex.by_id == {"cs1": SIG}


def test_garbage_and_responses_without_extra_content_teach_nothing_and_break_nothing():
    ex = proxy.ToolCallExtras()
    for raw in (b"", b"not json", b'data: {"choices": [{"message": {"content": "hi"}}]}\n\n', b'{"extra_content": 1}'):
        t = ex.tap()
        t.feed(raw)
        t.finish()
    assert ex.by_id == {} and ex.restore(b"not json tool_calls") == b"not json tool_calls"


class Fake(BaseHTTPRequestHandler):
    """A provider that, like Gemini 3, signs its tool calls and refuses a request that repeats one without the signature."""
    seen: list = []
    stream = False

    def log_message(self, *a):
        pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        Fake.seen.append(req)
        calls = [tc for m in req["messages"] for tc in (m.get("tool_calls") or [])]
        if calls and not all(tc.get("extra_content") == SIG for tc in calls):
            data = b'{"error": {"code": 400, "message": "Function call is missing a thought_signature"}}'
            self.send_response(400)
        elif calls:
            data = json.dumps({"choices": [{"message": {"content": "done"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 1}}).encode()
            self.send_response(200)
        else:
            call = {"id": "cx", "type": "function", "extra_content": SIG, "function": {"name": "f", "arguments": "{}"}}
            if Fake.stream:
                chunk = {"choices": [{"delta": {"role": "assistant", "tool_calls": [{"index": 0, **call}]}}]}
                data = f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode()
            else:
                data = json.dumps({"choices": [{"message": {"content": None, "tool_calls": [call]}}], "usage": {"prompt_tokens": 5, "completion_tokens": 1}}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if Fake.stream and not calls else "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _through_the_proxy(stream):
    Fake.seen, Fake.stream = [], stream
    up = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    srv = proxy.start("gemini", f"http://127.0.0.1:{up.server_address[1]}/v1", "k", {})
    try:
        first = _post(f"{srv.url}/chat/completions", {"model": "m", "messages": [{"role": "user", "content": "go"}], "stream": stream})
        echoed = [{"role": "user", "content": "go"}, {"role": "assistant", "content": None, "tool_calls": [{"id": "cx", "type": "function", "function": {"name": "f", "arguments": "{}"}}]},
                  {"role": "tool", "tool_call_id": "cx", "content": "r"}]
        second = _post(f"{srv.url}/chat/completions", {"model": "m", "messages": echoed})            # the harness drops extra_content, as OpenCode does
    finally:
        srv.stop()
        up.shutdown()
        up.server_close()
    return first, second


def test_through_the_whole_proxy_a_harness_that_drops_the_signature_still_gets_an_answer_json_and_streamed():
    for stream in (False, True):
        first, second = _through_the_proxy(stream)
        assert first[0] == 200 and second[0] == 200 and json.loads(second[1])["choices"][0]["message"]["content"] == "done", (stream, second)
        assert Fake.seen[1]["messages"][1]["tool_calls"][0]["extra_content"] == SIG


def test_without_the_memory_the_same_provider_would_have_refused():
    Fake.seen, Fake.stream = [], False
    up = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    try:
        echoed = [{"role": "assistant", "tool_calls": [{"id": "cx", "type": "function", "function": {"name": "f", "arguments": "{}"}}]}, {"role": "tool", "tool_call_id": "cx", "content": "r"}]
        assert _post(f"http://127.0.0.1:{up.server_address[1]}/v1/chat/completions", {"model": "m", "messages": echoed})[0] == 400
    finally:
        up.shutdown()
        up.server_close()
