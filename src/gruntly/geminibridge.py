"""A bridge that lets Gemini CLI use any OpenAI-compatible endpoint: a local model server, or gruntly's rate-limit proxy in front of a hosted provider.

Gemini CLI speaks only the Gemini API (`generateContent`, `streamGenerateContent`, `countTokens`) and can be pointed at another server of that API with
`GOOGLE_GEMINI_BASE_URL`. This is that server: a small local HTTP server that takes Gemini requests, turns each into one OpenAI chat completion for the
upstream endpoint, and turns the answer back. Nothing leaves the machine except what the upstream endpoint is already sent.

Translation (checked against the requests Gemini CLI really sends, see tests/unit/test_geminibridge.py):
  * `systemInstruction`                        -> one system message
  * `contents` role user: text parts           -> a user message (parts joined with a blank line)
  * `contents` role user: `functionResponse`   -> a `tool` message (`tool_call_id` = the call's id; the content is the response's `output` or its JSON)
  * `contents` role model: text / `functionCall` -> an assistant message with `content` / `tool_calls` (the CLI gives every call an id, and it is kept)
  * `tools[].functionDeclarations`             -> `tools` (`parametersJsonSchema`, or `parameters` with its upper-case type names lowered)
  * the OpenAI answer                          -> one candidate: a text part and a `functionCall` part per tool call, `usageMetadata` from `usage`
Left out on purpose: sampling settings (`temperature`, `topP`, `topK`: the CLI sends the Gemini defaults, which are wrong for most local models, so the
server's own defaults are used), thought parts, and streaming (the upstream answer is asked for whole and sent as a single event, which is a valid stream).
`countTokens` is estimated (4 characters a token); an upstream error is passed on in the Gemini error shape with the same code.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_PATH = re.compile(r"/v1(?:beta)?/models/([^:/?]+):(\w+)")
STATUS = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED", 404: "NOT_FOUND", 408: "DEADLINE_EXCEEDED", 429: "RESOURCE_EXHAUSTED",
          500: "INTERNAL", 502: "UNAVAILABLE", 503: "UNAVAILABLE", 504: "DEADLINE_EXCEEDED"}


def _lower_types(node):
    """Gemini's older schema spells types in capitals (OBJECT, STRING): OpenAI-style servers want JSON Schema's lower case."""
    if isinstance(node, dict):
        return {k: (v.lower() if k == "type" and isinstance(v, str) else _lower_types(v)) for k, v in node.items() if k != "$schema"}
    if isinstance(node, list):
        return [_lower_types(x) for x in node]
    return node


def tools_to_openai(tools) -> list[dict]:
    out = []
    for t in tools or []:
        for d in (t.get("functionDeclarations") or []) if isinstance(t, dict) else []:
            if not isinstance(d, dict) or not d.get("name"):
                continue
            schema = d.get("parametersJsonSchema") or d.get("parameters") or {"type": "object", "properties": {}}
            out.append({"type": "function", "function": {"name": d["name"], "description": d.get("description", ""), "parameters": _lower_types(schema)}})
    return out


def _text(parts) -> str:
    return "\n\n".join(p["text"] for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str) and not p.get("thought"))


def _tool_content(resp) -> str:
    if isinstance(resp, dict) and isinstance(resp.get("output"), str) and set(resp) <= {"output"}:
        return resp["output"]
    return json.dumps(resp, ensure_ascii=False)


def messages_to_openai(body: dict) -> list[dict]:
    msgs: list[dict] = []
    si = body.get("systemInstruction") or body.get("system_instruction")
    if isinstance(si, dict) and _text(si.get("parts") or []):
        msgs.append({"role": "system", "content": _text(si["parts"])})
    n = 0
    for c in body.get("contents") or []:
        if not isinstance(c, dict):
            continue
        parts = c.get("parts") or []
        if c.get("role") == "model":
            calls = []
            for p in parts:
                fc = p.get("functionCall") if isinstance(p, dict) else None
                if isinstance(fc, dict) and fc.get("name"):
                    n += 1
                    calls.append({"id": str(fc.get("id") or f"call_{n}"), "type": "function",
                                  "function": {"name": fc["name"], "arguments": json.dumps(fc.get("args") or {}, ensure_ascii=False)}})
            m: dict = {"role": "assistant", "content": _text(parts) or None}
            if calls:
                m["tool_calls"] = calls
            if m["content"] is None and not calls:
                m["content"] = ""
            msgs.append(m)
        else:
            prev_calls = next((m["tool_calls"] for m in reversed(msgs) if m.get("tool_calls")), [])      # a response without an id answers the call of the same name
            for p in parts:
                fr = p.get("functionResponse") if isinstance(p, dict) else None
                if isinstance(fr, dict):
                    cid = fr.get("id") or next((tc["id"] for tc in prev_calls if tc["function"]["name"] == fr.get("name")), f"call_{n}")
                    msgs.append({"role": "tool", "tool_call_id": str(cid), "content": _tool_content(fr.get("response"))})
            text = _text(parts)
            if text:
                msgs.append({"role": "user", "content": text})
    return msgs


def request_to_openai(body: dict, model: str) -> dict:
    out: dict = {"model": model, "messages": messages_to_openai(body), "stream": False}
    tools = tools_to_openai(body.get("tools"))
    if tools:
        out["tools"] = tools
    mo = (body.get("generationConfig") or {}).get("maxOutputTokens")
    if isinstance(mo, int) and mo > 0:
        out["max_tokens"] = mo
    return out


def response_from_openai(resp: dict, model: str = "") -> dict:
    choice = (resp.get("choices") or [{}])[0] if isinstance(resp, dict) else {}
    msg = choice.get("message") or {}
    parts: list[dict] = []
    if isinstance(msg.get("content"), str) and msg["content"]:
        parts.append({"text": msg["content"]})
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        parts.append({"functionCall": {"id": tc.get("id") or "", "name": fn.get("name", ""), "args": args if isinstance(args, dict) else {}}})
    if not parts:
        parts.append({"text": ""})
    u = resp.get("usage") if isinstance(resp.get("usage"), dict) else {}
    pt, ct = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
    out = {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "MAX_TOKENS" if choice.get("finish_reason") == "length" else "STOP", "index": 0}],
           "usageMetadata": {"promptTokenCount": pt, "candidatesTokenCount": ct, "totalTokenCount": pt + ct}, "modelVersion": model}
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens") if isinstance(u.get("prompt_tokens_details"), dict) else None
    if cached:
        out["usageMetadata"]["cachedContentTokenCount"] = int(cached)
    return out


def error_body(code: int, message: str) -> dict:
    return {"error": {"code": code, "message": message[:600], "status": STATUS.get(code, "UNKNOWN")}}


class Bridge:
    """A running bridge: `url` is what `GOOGLE_GEMINI_BASE_URL` takes; `stats` counts requests, errors and translated tool calls."""

    def __init__(self, upstream: str, key: str, timeout: float = 600.0):
        self.upstream = upstream.rstrip("/")
        self.key = key
        self.timeout = timeout
        self.stats = {"requests": 0, "errors": 0, "tool_calls": 0}
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code: int, obj, sse: bool = False):
                data = (f"data: {json.dumps(obj)}\r\n\r\n" if sse else json.dumps(obj)).encode()
                self.send_response(code)
                self.send_header("Content-Type", "text/event-stream" if sse else "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._send(404, error_body(404, f"the bridge does not serve {self.path.split('?')[0]}"))

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._send(400, error_body(400, "the request body is not JSON"))
                m = MODEL_PATH.search(self.path.split("?")[0])
                if not m:
                    return self._send(404, error_body(404, f"the bridge does not serve {self.path.split('?')[0]}"))
                model, action = m.group(1), m.group(2)
                outer.stats["requests"] += 1
                if action == "countTokens":
                    est = len(json.dumps(body.get("contents") or [])) // 4 + len(json.dumps(body.get("systemInstruction") or "")) // 4
                    return self._send(200, {"totalTokens": max(est, 1)})
                if action not in ("generateContent", "streamGenerateContent"):
                    return self._send(404, error_body(404, f"the bridge does not serve {action}"))
                try:
                    resp = outer.complete(request_to_openai(body, model))
                except urllib.error.HTTPError as e:
                    outer.stats["errors"] += 1
                    return self._send(e.code, error_body(e.code, e.read().decode("utf8", "replace")))
                except (urllib.error.URLError, OSError, TimeoutError) as e:
                    outer.stats["errors"] += 1
                    return self._send(503, error_body(503, f"the upstream endpoint is unreachable: {e}"))
                out = response_from_openai(resp, model)
                outer.stats["tool_calls"] += sum(1 for p in out["candidates"][0]["content"]["parts"] if "functionCall" in p)
                self._send(200, out, sse=action == "streamGenerateContent")

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def complete(self, payload: dict) -> dict:
        req = urllib.request.Request(self.upstream + "/chat/completions", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def stop(self) -> dict:
        self.srv.shutdown()
        self.srv.server_close()
        return dict(self.stats)


def start(upstream: str, key: str, timeout: float = 600.0) -> Bridge:
    return Bridge(upstream, key, timeout)
