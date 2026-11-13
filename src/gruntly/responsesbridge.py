"""A bridge that lets Codex CLI use any OpenAI-compatible chat endpoint: Codex dropped the chat API and speaks only the Responses API, which almost no provider
outside OpenAI serves. This is a small local server that takes Codex's `POST /v1/responses`, turns each request into one chat completion for the upstream
endpoint, and sends the answer back as the stream of Responses events Codex reads. Nothing leaves the machine except what the upstream is already sent.

Translation (checked against the requests Codex 0.167.2 really sends, see tests/unit/test_responsesbridge.py):
  * `instructions`, and `developer` / `system` messages up front -> one system message (a developer message later in the conversation becomes a user message:
    some local chat templates refuse a system message that is not first)
  * `message` user / assistant (`input_text`, `output_text`)    -> user / assistant messages
  * `function_call` items (and `custom_tool_call`)               -> one assistant message with `tool_calls` (an assistant text just before them is kept)
  * `function_call_output` (and `custom_tool_call_output`)       -> `tool` messages
  * `tools` of type function                                     -> chat `tools` (a `custom` tool becomes a function taking one string, `input`);
    hosted and namespace tools (`web_search`, `multi_agent_v1`) are dropped: no chat provider can serve them
  * the chat answer -> `message` and `function_call` output items, `usage` (cached and reasoning tokens kept); what a provider attaches to a tool call
    (`extra_content`, Gemini's `thought_signature`) is remembered by call id and put back when Codex echoes the call, which Gemini 3 requires
Left out on purpose: `reasoning` items (skipped both ways), `store`, `include`, `prompt_cache_key`, and true streaming (the upstream answer is asked for whole
and sent as the events of a finished response, which is a valid stream).

As a wrapper: `python -m gruntly.responsesbridge --upstream URL [--key-env VAR] -- COMMAND ...` starts the bridge, replaces `{bridge_url}` in the command with its
address, runs the command with the same standard streams and exits with its code. That is how a launched parent (Codex) uses it without anyone owning its lifetime.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _text(content) -> str:
    if isinstance(content, str):
        return content
    out = []
    for p in content or []:
        if isinstance(p, dict):
            if isinstance(p.get("text"), str):
                out.append(p["text"])
            elif p.get("type") in ("input_image", "image_url"):
                out.append("[image omitted]")
    return "\n".join(out)


def tools_to_openai(tools) -> list[dict]:
    out = []
    for t in tools or []:
        if not isinstance(t, dict) or not t.get("name"):
            continue
        if t.get("type") == "function":
            out.append({"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                                         "parameters": t.get("parameters") or {"type": "object", "properties": {}}}})
        elif t.get("type") == "custom":
            out.append({"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                                         "parameters": {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]}}})
    return out


def input_to_messages(body: dict, extras: dict | None = None) -> list[dict]:
    msgs: list[dict] = []
    if isinstance(body.get("instructions"), str) and body["instructions"].strip():
        msgs.append({"role": "system", "content": body["instructions"]})
    items = body.get("input")
    if isinstance(items, str):
        items = [{"type": "message", "role": "user", "content": items}]
    seen_non_system = False
    custom_ids: set[str] = set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        t = it.get("type") or ("message" if it.get("role") else "")
        if t == "message":
            role, text = it.get("role"), _text(it.get("content"))
            if role in ("developer", "system"):
                if not seen_non_system:
                    if msgs and msgs[-1]["role"] == "system":
                        msgs[-1]["content"] += "\n\n" + text
                    else:
                        msgs.append({"role": "system", "content": text})
                else:
                    msgs.append({"role": "user", "content": text})
            else:
                seen_non_system = True
                msgs.append({"role": "assistant" if role == "assistant" else "user", "content": text})
        elif t in ("function_call", "custom_tool_call"):
            seen_non_system = True
            raw = it.get("arguments") if t == "function_call" else json.dumps({"input": it.get("input", "")})
            call = {"id": str(it.get("call_id") or it.get("id") or f"call_{uuid.uuid4().hex[:8]}"), "type": "function",
                    "function": {"name": it.get("name", ""), "arguments": raw if isinstance(raw, str) else json.dumps(raw or {})}}
            if extras and call["id"] in extras:                  # what the provider attached to this call (Gemini's thought_signature) goes back unchanged
                call["extra_content"] = extras[call["id"]]
            if t == "custom_tool_call":
                custom_ids.add(call["id"])
            if msgs and msgs[-1]["role"] == "assistant":          # an assistant text just before the calls, or an earlier call of the same turn
                msgs[-1].setdefault("tool_calls", []).append(call)
            else:
                msgs.append({"role": "assistant", "content": None, "tool_calls": [call]})
        elif t in ("function_call_output", "custom_tool_call_output"):
            seen_non_system = True
            out = it.get("output")
            msgs.append({"role": "tool", "tool_call_id": str(it.get("call_id") or ""), "content": out if isinstance(out, str) else _text(out) if isinstance(out, list) else json.dumps(out)})
        # reasoning items and anything else: skipped
    for m in msgs:                                                 # an assistant message that only calls tools has no text: null, not ""
        if m["role"] == "assistant" and m.get("tool_calls") and not m.get("content"):
            m["content"] = None
    return msgs


def request_to_openai(body: dict, extras: dict | None = None) -> dict:
    out: dict = {"model": body.get("model", ""), "messages": input_to_messages(body, extras), "stream": False}
    tools = tools_to_openai(body.get("tools"))
    if tools:
        out["tools"] = tools
        if body.get("parallel_tool_calls") is False:
            out["parallel_tool_calls"] = False
    if isinstance(body.get("max_output_tokens"), int) and body["max_output_tokens"] > 0:
        out["max_tokens"] = body["max_output_tokens"]
    return out


def response_items(resp: dict, custom_names: set[str] | None = None, extras: dict | None = None) -> tuple[list[dict], dict]:
    """(output items, Responses-shaped usage) for a chat completion. `extras` collects what the provider attached to each tool call (`extra_content`)."""
    msg = ((resp.get("choices") or [{}])[0]).get("message") or {}
    items: list[dict] = []
    if isinstance(msg.get("content"), str) and msg["content"].strip():
        items.append({"type": "message", "id": f"msg_{uuid.uuid4().hex[:12]}", "status": "completed", "role": "assistant",
                      "content": [{"type": "output_text", "text": msg["content"], "annotations": []}]})
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        cid = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
        if extras is not None and tc.get("extra_content"):
            extras[cid] = tc["extra_content"]
        if custom_names and fn.get("name") in custom_names:
            try:
                arg = json.loads(fn.get("arguments") or "{}").get("input", "")
            except ValueError:
                arg = fn.get("arguments") or ""
            items.append({"type": "custom_tool_call", "id": f"ctc_{uuid.uuid4().hex[:12]}", "status": "completed", "call_id": cid, "name": fn.get("name", ""), "input": arg})
        else:
            items.append({"type": "function_call", "id": f"fc_{uuid.uuid4().hex[:12]}", "status": "completed", "call_id": cid, "name": fn.get("name", ""),
                          "arguments": fn.get("arguments") if isinstance(fn.get("arguments"), str) else json.dumps(fn.get("arguments") or {})})
    u = resp.get("usage") if isinstance(resp.get("usage"), dict) else {}
    pt, ct = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
    pd = u.get("prompt_tokens_details") if isinstance(u.get("prompt_tokens_details"), dict) else {}
    cd = u.get("completion_tokens_details") if isinstance(u.get("completion_tokens_details"), dict) else {}
    usage = {"input_tokens": pt, "output_tokens": ct, "total_tokens": pt + ct, "input_tokens_details": {"cached_tokens": int(pd.get("cached_tokens") or 0)},
             "output_tokens_details": {"reasoning_tokens": int(cd.get("reasoning_tokens") or 0)}}
    return items, usage


def events(items: list[dict], usage: dict, model: str) -> list[tuple[str, dict]]:
    """The Responses stream for a finished answer, as (event name, data) pairs."""
    rid = f"resp_{uuid.uuid4().hex[:16]}"
    base = {"id": rid, "object": "response", "model": model}
    ev: list[tuple[str, dict]] = [("response.created", {"type": "response.created", "response": {**base, "status": "in_progress", "output": []}})]
    for i, it in enumerate(items):
        if it["type"] == "message":
            ev.append(("response.output_item.added", {"type": "response.output_item.added", "output_index": i, "item": {**it, "status": "in_progress", "content": []}}))
            text = it["content"][0]["text"]
            ev.append(("response.output_text.delta", {"type": "response.output_text.delta", "item_id": it["id"], "output_index": i, "content_index": 0, "delta": text}))
            ev.append(("response.output_text.done", {"type": "response.output_text.done", "item_id": it["id"], "output_index": i, "content_index": 0, "text": text}))
        else:
            ev.append(("response.output_item.added", {"type": "response.output_item.added", "output_index": i,
                                                     "item": {**it, "status": "in_progress", **({"arguments": ""} if it["type"] == "function_call" else {"input": ""})}}))
        ev.append(("response.output_item.done", {"type": "response.output_item.done", "output_index": i, "item": it}))
    ev.append(("response.completed", {"type": "response.completed", "response": {**base, "status": "completed", "output": items, "usage": usage}}))
    return ev


def error_body(code: int, message: str) -> dict:
    return {"error": {"message": message[:600], "type": "invalid_request_error" if code < 500 else "server_error", "code": str(code)}}


class Bridge:
    """A running bridge: `url` ends in /v1 (what a provider's `base_url` takes); `stats` counts requests, errors and translated tool calls."""

    def __init__(self, upstream: str, key: str, timeout: float = 600.0):
        self.upstream = upstream.rstrip("/")
        self.key = key
        self.timeout = timeout
        self.stats = {"requests": 0, "errors": 0, "tool_calls": 0}
        self.extras: dict[str, dict] = {}          # call id -> the provider's extra_content for it (Gemini 3 refuses a tool call echoed back without its thought_signature)
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _json(self, code: int, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path = self.path.split("?")[0]
                if path.rstrip("/").endswith("/models"):
                    try:
                        req = urllib.request.Request(outer.upstream + "/models", headers={"Authorization": f"Bearer {outer.key}"})
                        with urllib.request.urlopen(req, timeout=30) as r:
                            data = r.read()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                        return
                    except (urllib.error.URLError, OSError):
                        pass
                self._json(404, error_body(404, f"the bridge does not serve {path}"))

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._json(400, error_body(400, "the request body is not JSON"))
                if not self.path.split("?")[0].rstrip("/").endswith("/responses"):
                    return self._json(404, error_body(404, f"the bridge does not serve {self.path.split('?')[0]}"))
                outer.stats["requests"] += 1
                custom = {t["name"] for t in body.get("tools") or [] if isinstance(t, dict) and t.get("type") == "custom" and t.get("name")}
                try:
                    resp = outer.complete(request_to_openai(body, outer.extras))
                except urllib.error.HTTPError as e:
                    outer.stats["errors"] += 1
                    return self._json(e.code, error_body(e.code, e.read().decode("utf8", "replace")))
                except (urllib.error.URLError, OSError, TimeoutError) as e:
                    outer.stats["errors"] += 1
                    return self._json(503, error_body(503, f"the upstream endpoint is unreachable: {e}"))
                items, usage = response_items(resp, custom, outer.extras)
                outer.stats["tool_calls"] += sum(1 for i in items if i["type"] != "message")
                data = "".join(f"event: {name}\ndata: {json.dumps(d)}\n\n" for name, d in events(items, usage, body.get("model", ""))).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/v1"
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


def main(argv: list[str] | None = None) -> int:
    """The wrapper: start the bridge, run COMMAND with `{bridge_url}` filled in, stop the bridge, exit with the command's code."""
    ap = argparse.ArgumentParser(prog="gruntly.responsesbridge")
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--key-env", default="")
    ap.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        print("gruntly.responsesbridge: no command to run", file=sys.stderr)
        return 2
    key = os.environ.get(a.key_env, "") if a.key_env else "local"
    if a.key_env and not key:
        print(f"gruntly.responsesbridge: {a.key_env} is not set", file=sys.stderr)
        return 2
    b = start(a.upstream, key)
    try:
        return subprocess.run([c.replace("{bridge_url}", b.url) for c in cmd]).returncode
    except FileNotFoundError as e:
        print(f"gruntly.responsesbridge: cannot run {cmd[0]}: {e}", file=sys.stderr)
        return 127
    finally:
        b.stop()


if __name__ == "__main__":
    raise SystemExit(main())
