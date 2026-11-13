"""A stub model server that records what a harness actually sends, so a harness's setup can be checked for real with no key and no cost.

A harness that is told to use a lean setup (its own system prompt replaced, only a shell tool left, extensions off) either does it or it
does not; reading its documentation does not settle that, and a live model call costs money. This server speaks the OpenAI chat
completions and responses protocols just well enough for a harness to complete one turn (it answers `ok`), and records each request: the
system prompt, the names of the tools offered, the model, whether it streamed. Point a harness at it, run one task, read `server.requests`.

Not a model: it never calls a tool and never answers anything but `ok`.
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
    return s


class StubServer:
    def __init__(self, reply: str = REPLY):
        self.requests: list[Seen] = []
        self.reply = reply
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
                seen.auth = self.headers.get("Authorization", "")
                outer.requests.append(seen)
                usage = {"prompt_tokens": 7, "completion_tokens": 1, "total_tokens": 8}
                if self.path.rstrip("/").endswith("/responses"):
                    return self._responses(body, outer.reply)
                if body.get("stream"):
                    chunks = [{"id": "stub", "object": "chat.completion.chunk", "model": "stub-model",
                               "choices": [{"index": 0, "delta": {"role": "assistant", "content": outer.reply}, "finish_reason": None}]},
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
                                 "choices": [{"index": 0, "message": {"role": "assistant", "content": outer.reply}, "finish_reason": "stop"}]})

            def _responses(self, body, reply):
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
        return [r for r in self.requests if r.path.rstrip("/").endswith(("/chat/completions", "/responses"))]

    def stop(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.stop()
