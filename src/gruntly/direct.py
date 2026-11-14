"""A lean delegating parent with no harness at all: a short loop that calls an OpenAI-compatible chat API (any provider in the catalog, or a local
server) with ONE tool, `bash`, that runs `gruntly` commands and nothing else.

Why it exists: every harness brings a system prompt and a tool list of its own, and the parent re-reads them on every turn, which is most of a
parent's cost. This loop sends exactly the delegating prompt and one small tool, and costs the same for any provider; it is also the one parent
whose dollars gruntly can work out itself, because it sees every response's `usage`. It is meant for people who have a key and no agent harness,
and as the cheapest baseline for the parents that do.

What the tool accepts: one `gruntly ...` command, run WITHOUT a shell (so nothing can be chained, piped, redirected or substituted), with one
optional heredoc (`<<'EOF' ... EOF`) whose body becomes the command's standard input (a long request). Anything else
is refused with the reason, and the model sees the refusal. Run as `python -m gruntly.direct`; the task is on stdin, one JSON object comes back on
stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import pricing, providers
from .parents import prompts
from .usage import Usage, parse_usage

TOOL = {"type": "function", "function": {
    "name": "bash", "description": "Run one gruntly command. Only commands that start with `gruntly` are run; nothing can be chained or piped.",
    "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "the gruntly command"}}, "required": ["command"]}}}
MAX_TURNS = 16
RESULT_CHARS = 20000
CALL_TIMEOUT_S = 1200
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1[ \t]*(?:\r?\n|$)")


class Refused(ValueError):
    pass


def _find_heredoc(cmd: str):
    """The heredoc marker outside quotes: (start of marker, tag, index just after the marker's line) or None."""
    quote, i = None, 0
    while i < len(cmd):
        c = cmd[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in ("'", '"'):
            quote = c
        elif c == "\\":
            i += 2
            continue
        elif cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            m = HEREDOC.match(cmd, i)
            if m:
                return i, m.group(2), m.end()
        i += 1
    return None


def parse_command(cmd: str) -> tuple[list[str], str | None]:
    """(argv after `gruntly`, standard input) for an acceptable command; raises Refused with the reason otherwise."""
    cmd = (cmd or "").strip()
    stdin = None
    hd = _find_heredoc(cmd)
    if hd:
        start, tag, body_at = hd
        lines = cmd[body_at:].splitlines()
        if tag not in [ln.strip() for ln in lines]:
            raise Refused(f"the heredoc `<<{tag}` is never closed by a line that says {tag}")
        end = [ln.strip() for ln in lines].index(tag)
        stdin = "\n".join(lines[:end]) + "\n"
        rest = "\n".join(lines[end + 1:]).strip()
        if rest:
            raise Refused("nothing may follow the heredoc: one gruntly command only")
        cmd = cmd[:start].strip()
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError as e:
        raise Refused(f"the command does not parse: {e}") from None
    if not toks or toks[0] != "gruntly":
        raise Refused("only commands that start with `gruntly` are run")
    bad = [t for t in toks if set(t) <= set(";&|<>()")]
    if bad:
        raise Refused(f"`{bad[0]}` is not allowed: one gruntly command only, with no chaining, piping or redirection")
    return toks[1:], stdin


def run_gruntly(args: list[str], stdin: str | None) -> str:
    exe = shutil.which("gruntly")
    argv = ([exe] if exe else [sys.executable, "-m", "gruntly"]) + args
    try:
        p = subprocess.run(argv, input=stdin, capture_output=True, text=True, encoding="utf8", errors="replace", timeout=CALL_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return f"gruntly did not finish in {CALL_TIMEOUT_S} s"
    out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr and p.returncode else "")
    out = out.strip() or f"(no output, exit code {p.returncode})"
    return out if len(out) <= RESULT_CHARS else out[:RESULT_CHARS // 2] + "\n...[cut]...\n" + out[-RESULT_CHARS // 2:]


def post(url: str, key: str, body: dict, retries: int = 3) -> dict:
    """One chat completion; a 429 or 5xx is retried a few times with a short wait."""
    data = json.dumps(body).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf8", "replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep((1, 3, 8)[min(attempt, 2)])
                continue
            raise RuntimeError(f"HTTP {e.code} from the model: {detail}") from None
        except (urllib.error.URLError, OSError) as e:
            if attempt < retries:
                time.sleep((1, 3, 8)[min(attempt, 2)])
                continue
            raise RuntimeError(f"the model endpoint is unreachable: {e}") from None
    raise RuntimeError("unreachable")


def run_loop(task: str, base_url: str, key: str, model: str, max_turns: int = MAX_TURNS, send=post, run=run_gruntly) -> dict:
    messages = [{"role": "system", "content": prompts.DELEGATING}, {"role": "user", "content": task}]
    usage = Usage()
    final, error, turns, refused = "", False, 0, 0
    url = base_url.rstrip("/") + "/chat/completions"
    for _ in range(max_turns):
        try:
            resp = send(url, key, {"model": model, "messages": messages, "tools": [TOOL]})
        except RuntimeError as e:
            return {"final_message": str(e), "is_error": True, "turns": turns, "refused": refused, "usage": usage_dict(usage)}
        turns += 1
        u = parse_usage(resp)
        if u is None:
            usage.missing += 1
            usage.requests += 1
        else:
            u.requests = 1
            usage.add(u)
        msg = ((resp.get("choices") or [{}])[0]).get("message") or {}
        messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls") and v is not None} or {"role": "assistant", "content": ""})
        calls = msg.get("tool_calls") or []
        if not calls:
            final = str(msg.get("content") or "").strip()
            break
        for c in calls:
            fn = c.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
                args, stdin = parse_command(str(args.get("command", "")))
                result = run(args, stdin) if fn.get("name") == "bash" else f"unknown tool {fn.get('name')!r}"
            except Refused as e:
                refused += 1
                result = f"refused: {e}"
            except (ValueError, AttributeError):
                refused += 1
                result = "refused: the tool arguments must be a JSON object with a `command` string"
            messages.append({"role": "tool", "tool_call_id": c.get("id") or "call", "content": result})
    else:
        error = True
        final = f"stopped after {max_turns} turns without a final answer"
    return {"final_message": final, "is_error": error, "turns": turns, "refused": refused, "usage": usage_dict(usage)}


def usage_dict(u: Usage) -> dict:
    return {"prompt": u.prompt, "completion": u.completion, "cached": u.cached, "cache_write": u.cache_write, "reasoning": u.reasoning,
            "requests": u.requests, "missing": u.missing, "cost_usd": u.cost_usd}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gruntly.direct")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--key-env", default="")
    ap.add_argument("--provider", default="")
    ap.add_argument("--max-turns", type=int, default=MAX_TURNS)
    a = ap.parse_args(argv)
    key = os.environ.get(a.key_env, "") if a.key_env else "local"
    if a.key_env and not key:
        print(json.dumps({"final_message": f"no API key: {a.key_env} is not set", "is_error": True, "turns": 0, "usage": usage_dict(Usage())}))
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    res = run_loop(sys.stdin.read(), a.base_url, key, a.model, a.max_turns)
    if a.provider:                                   # dollars: the provider's own figure, a price, or unknown (a provider not in the catalog is hosted and unpriced)
        p = providers.ALL.get(a.provider)
        u = Usage(prompt=res["usage"]["prompt"], completion=res["usage"]["completion"], cached=res["usage"]["cached"], requests=res["usage"]["requests"],
                  missing=res["usage"]["missing"], cost_usd=res["usage"]["cost_usd"])
        c = pricing.cost(u, a.provider, a.model, p.kind if p else "hosted")
        res["cost"] = {"usd": c.usd, "source": c.source, "detail": c.detail}
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
