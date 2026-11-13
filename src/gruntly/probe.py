"""A stub model server that records what a harness actually sends, so a harness's setup can be checked for real with no key and no cost.

A harness that is told to use a lean setup (its own system prompt replaced, only a shell tool left, extensions off) either does it or it
does not; reading its documentation does not settle that, and a live model call costs money. This server speaks the OpenAI chat
completions and responses protocols just well enough for a harness to complete one turn (it answers `ok`), and records each request: the
system prompt, the names of the tools offered, the model, whether it streamed. Point a harness at it, run one task, read `server.requests`.

Not a model. By default it answers `ok` and never calls a tool. With a `script` it plays one: each step is either a final text or a tool call
(`{"tool": "bash", "args": {"command": "..."}}`), used on the requests that offer tools (a harness's tool-less title or summary requests are
answered `ok` and do not use up a step). The request that follows a tool call carries the harness's answer to it (`Seen.tool_results`): that is
how a restriction such as "only gruntly commands may run" is checked, by asking for a command that must be refused and one that must not.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPLY = "ok"


@dataclass
class Seen:
    path: str
    model: str | None = None
    system: str = ""                                  # system and developer messages, joined
    user: str = ""                                    # the last user message
    tools: list[str] = field(default_factory=list)    # names of the tools offered
    stream: bool = False
    auth: str = ""                                    # the Authorization header (a dummy key in tests): how key plumbing is checked
    tool_results: list[str] = field(default_factory=list)   # what the harness answered to the tool calls the script made (chat requests)
    raw: dict = field(default_factory=dict)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return ""


def _tool_names(tools) -> list[str]:
    out = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        if isinstance(t.get("functionDeclarations"), list):          # Gemini: {functionDeclarations: [{name}]}
            out += [str(d["name"]) for d in t["functionDeclarations"] if isinstance(d, dict) and d.get("name")]
            continue
        fn = t.get("function") if isinstance(t.get("function"), dict) else t        # chat: {function: {name}}, responses: {name}
        if fn.get("name"):
            out.append(str(fn["name"]))
        elif t.get("type"):
            out.append(str(t["type"]))
    return out


def summarize(path: str, body: dict) -> Seen:
    s = Seen(path=path, model=body.get("model"), stream=bool(body.get("stream")), raw=body)
    msgs = body.get("messages")
    if isinstance(msgs, list):                         # chat completions
        s.system = "\n".join(_text(m.get("content")) for m in msgs if isinstance(m, dict) and m.get("role") in ("system", "developer"))
        users = [m for m in msgs if isinstance(m, dict) and m.get("role") == "user"]
        s.user = _text(users[-1].get("content")) if users else ""
    elif isinstance(body.get("contents"), list):       # Gemini API (generateContent)
        si = body.get("systemInstruction") or body.get("system_instruction") or {}
        s.system = _text(si.get("parts") if isinstance(si, dict) else si)
        users = [c for c in body["contents"] if isinstance(c, dict) and c.get("role") == "user" and any("text" in p for p in c.get("parts", []) if isinstance(p, dict))]
        s.user = _text(users[-1].get("parts")) if users else ""
        s.tool_results = [json.dumps(p["functionResponse"].get("response"), default=str) for c in body["contents"] if isinstance(c, dict)
                          for p in c.get("parts", []) if isinstance(p, dict) and isinstance(p.get("functionResponse"), dict)]
    else:                                              # responses API
        s.system = str(body.get("instructions") or "")
        inp = body.get("input")
        if isinstance(inp, str):
            s.user = inp
        elif isinstance(inp, list):
            for m in inp:
                if isinstance(m, dict) and m.get("role") in ("system", "developer"):
                    s.system += ("\n" if s.system else "") + _text(m.get("content"))
                elif isinstance(m, dict) and m.get("role") == "user":
                    s.user = _text(m.get("content"))
    s.tools = _tool_names(body.get("tools"))
    if isinstance(msgs, list):
        s.tool_results = [_text(m.get("content")) for m in msgs if isinstance(m, dict) and m.get("role") == "tool"]
    elif isinstance(body.get("input"), list):                  # responses API: the harness's answers are `function_call_output` items
        s.tool_results = [_text(m.get("output")) for m in body["input"] if isinstance(m, dict) and m.get("type") in ("function_call_output", "custom_tool_call_output")]
    return s


class StubServer:
    def __init__(self, reply: str = REPLY, script: list | None = None):
        self.requests: list[Seen] = []
        self.reply = reply
        self.script = list(script or [])
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path.rstrip("/").endswith("/models"):
                    return self._json(200, {"object": "list", "data": [{"id": "stub-model", "object": "model", "owned_by": "stub"}]})
                self._json(404, {"error": "not found"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    body = {}
                seen = summarize(self.path, body)
                seen.auth = self.headers.get("Authorization", "") or self.headers.get("x-goog-api-key", "")
                outer.requests.append(seen)
                if ":countTokens" in self.path:
                    return self._json(200, {"totalTokens": 7})
                usage = {"prompt_tokens": 7, "completion_tokens": 1, "total_tokens": 8}
                step = outer.script.pop(0) if outer.script and seen.tools else None
                is_responses = self.path.rstrip("/").endswith("/responses")
                if "generateContent" in self.path or "streamGenerateContent" in self.path:
                    return self._gemini(step if isinstance(step, dict) and step.get("tool") else (step if isinstance(step, str) else outer.reply), "streamGenerateContent" in self.path)
                if isinstance(step, dict) and step.get("tool"):
                    return self._responses(body, "", step) if is_responses else self._tool_call(body, step, usage)
                if isinstance(step, str):
                    outer_reply = step
                else:
                    outer_reply = outer.reply
                if is_responses:
                    return self._responses(body, outer_reply)
                if body.get("stream"):
                    chunks = [{"id": "stub", "object": "chat.completion.chunk", "model": "stub-model",
                               "choices": [{"index": 0, "delta": {"role": "assistant", "content": outer_reply}, "finish_reason": None}]},
                              {"id": "stub", "object": "chat.completion.chunk", "model": "stub-model",
                               "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": usage}]
                    data = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks).encode() + b"data: [DONE]\n\n"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self._json(200, {"id": "stub", "object": "chat.completion", "model": "stub-model", "usage": usage,
                                 "choices": [{"index": 0, "message": {"role": "assistant", "content": outer_reply}, "finish_reason": "stop"}]})

            def _tool_call(self, body, step, usage):
                call = {"id": "call_stub_1", "type": "function", "function": {"name": step["tool"], "arguments": json.dumps(step.get("args") or {})}}
                if body.get("stream"):
                    chunks = [{"id": "stub", "object": "chat.completion.chunk", "model": "stub-model",
                               "choices": [{"index": 0, "delta": {"role": "assistant", "tool_calls": [{**call, "index": 0}]}, "finish_reason": None}]},
                              {"id": "stub", "object": "chat.completion.chunk", "model": "stub-model",
                               "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}], "usage": usage}]
                    data = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks).encode() + b"data: [DONE]\n\n"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self._json(200, {"id": "stub", "object": "chat.completion", "model": "stub-model", "usage": usage,
                                 "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "tool_calls": [call]}, "finish_reason": "tool_calls"}]})

            def _gemini(self, step, stream):
                part = {"functionCall": {"name": step["tool"], "args": step.get("args") or {}}} if isinstance(step, dict) else {"text": step}
                obj = {"candidates": [{"content": {"role": "model", "parts": [part]}, "finishReason": "STOP", "index": 0}],
                       "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 1, "totalTokenCount": 8}, "modelVersion": "stub-model"}
                if stream:
                    data = f"data: {json.dumps(obj)}\r\n\r\n".encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self._json(200, obj)

            def _responses(self, body, reply, step=None):
                if step:                                       # play a model that calls a tool (a function call item) instead of answering
                    msg = {"type": "function_call", "id": "fc_stub_1", "call_id": "call_stub_1", "status": "completed", "name": step["tool"],
                           "arguments": json.dumps(step.get("args") or {})}
                else:
                    msg = {"type": "message", "id": "msg_stub", "status": "completed", "role": "assistant",
                           "content": [{"type": "output_text", "text": reply, "annotations": []}]}
                resp = {"id": "resp_stub", "object": "response", "status": "completed", "model": "stub-model", "output": [msg],
                        "usage": {"input_tokens": 7, "output_tokens": 1, "total_tokens": 8}}
                if body.get("stream"):
                    events = [("response.created", {"type": "response.created", "response": {**resp, "status": "in_progress", "output": []}}),
                              ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": msg}),
                              ("response.completed", {"type": "response.completed", "response": resp})]
                    data = "".join(f"event: {n}\ndata: {json.dumps(e)}\n\n" for n, e in events).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self._json(200, resp)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def chat(self) -> list[Seen]:
        """The model requests (not listings): what the harness sent as its turn."""
        return [r for r in self.requests if r.path.rstrip("/").endswith(("/chat/completions", "/responses")) or "generateContent" in r.path or "streamGenerateContent" in r.path]

    def stop(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.stop()
