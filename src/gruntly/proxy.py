"""A tiny local proxy in front of a hosted OpenAI-compatible endpoint.

Why a proxy: the child harness (OpenCode, Qwen Code, ...) makes its own requests, so gruntly cannot pace them from the
outside. Pointing the child at this proxy lets gruntly (a) keep the real API key out of the child, the run spec and the
logs, (b) wait instead of failing when the per-minute limits are reached, (c) retry a 429 after the delay the provider
names, (d) stop cleanly when the daily quota is spent, and (e) count what a run used.

Streaming is passed through as it arrives. The proxy speaks HTTP/1.0 (the body ends when the connection closes), which
every client handles and which avoids re-framing a chunked stream.
"""
from __future__ import annotations

import http.client
import json
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

MAX_WAIT_S = 120          # never sleep longer than this for one request; return the 429 instead
MAX_RETRIES = 3
RETRY_5XX = (500, 502, 503, 504)
TOKEN_CHARS = 3.5         # request characters per token, for the per-minute token budget


def _pacific_day() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001 - no tz database: UTC-8 is close enough for a daily counter
        return (datetime.now(timezone.utc) - timedelta(hours=8)).strftime("%Y-%m-%d")


class Limiter:
    """Sliding one-minute windows for requests and tokens, plus a per-day request count saved to disk."""

    def __init__(self, rpm=None, tpm=None, rpd=None, state: Path | None = None, clock=time.monotonic, sleep=time.sleep):
        self.rpm, self.tpm, self.rpd = rpm, tpm, rpd
        self.state, self.clock, self.sleep = state, clock, sleep
        self.win: deque[tuple[float, int]] = deque()
        self.lock = threading.Lock()
        self.on_wait = None          # optional callable(seconds, why) so a UI can say why nothing is happening
        self.stats = {"requests": 0, "retries_429": 0, "waited_s": 0.0, "tokens_est": 0, "denied": 0, "retries_5xx": 0}

    # ---- daily count (survives runs) ----
    def _day(self) -> dict:
        try:
            d = json.loads(self.state.read_text(encoding="utf8")) if self.state else {}
        except (OSError, ValueError):
            d = {}
        return d if d.get("day") == _pacific_day() else {"day": _pacific_day(), "count": 0}

    def daily_left(self) -> int | None:
        return None if self.rpd is None else max(self.rpd - self._day()["count"], 0)

    def _bump(self) -> None:
        if not self.state:
            return
        d = self._day()
        d["count"] += 1
        try:
            self.state.parent.mkdir(parents=True, exist_ok=True)
            self.state.write_text(json.dumps(d), encoding="utf8")
        except OSError:
            pass

    # ---- per-minute pacing ----
    def _delay(self, tokens: int) -> float:
        now = self.clock()
        while self.win and now - self.win[0][0] >= 60:
            self.win.popleft()
        if not self.win:
            return 0.0                      # an empty window always lets one request through, however large
        need = 0.0
        if self.rpm and len(self.win) >= self.rpm:
            need = max(need, 60 - (now - self.win[0][0]))
        if self.tpm:
            used, i = sum(t for _, t in self.win), 0
            rows = list(self.win)
            while used + tokens > self.tpm and i < len(rows):
                used -= rows[i][1]
                need = max(need, 60 - (now - rows[i][0]))
                i += 1
        return need

    def acquire(self, tokens: int) -> bool:
        """Block until a request of about `tokens` fits. False when the daily quota is spent."""
        if self.rpd is not None and self.daily_left() == 0:
            self.stats["denied"] += 1
            return False
        while True:
            with self.lock:
                d = self._delay(tokens)
                if d <= 0:
                    self.win.append((self.clock(), tokens))
                    self._bump()
                    self.stats["requests"] += 1
                    self.stats["tokens_est"] += tokens
                    return True
            d = min(d + 0.2, MAX_WAIT_S)
            self.stats["waited_s"] += d
            if self.on_wait:
                self.on_wait(round(d), "provider rate limit")
            self.sleep(d)


def dedupe_keys(body: bytes) -> bytes:
    """Repair a JSON request body that repeats a key inside one object. Hermes can send `reasoning_content` twice when it replays
    a reasoning model's earlier turn, and strict providers (Poolside's Laguna on NVIDIA) answer HTTP 400 "duplicate field".
    The last value wins, as in every JSON parser. A body with no repeat is returned untouched, byte for byte."""
    repeated = []

    def pairs(items):
        if len({k for k, _ in items}) != len(items):
            repeated.append(1)
        d = dict(items)
        if "reasoning" in d and "reasoning_content" in d:      # the provider reads `reasoning` as an alias of `reasoning_content`
            del d["reasoning"]
            repeated.append(1)
        return d

    try:
        obj = json.loads(body, object_pairs_hook=pairs)
    except (ValueError, UnicodeDecodeError):
        return body
    return json.dumps(obj, ensure_ascii=False).encode("utf8") if repeated else body


def retry_after(headers, body: bytes) -> float:
    """Seconds a 429 asks us to wait: Retry-After, else 'retry in 12.3s' / retryDelay '12s' in the body, else 20."""
    v = headers.get("Retry-After") if headers else None
    if v:
        try:
            return float(v)
        except ValueError:
            pass
    m = re.search(rb"(?:retry in|retryDelay\"?:\s*\")\s*([0-9.]+)\s*s", body or b"", re.I)
    return float(m.group(1)) if m else 20.0


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server: "ProxyServer"

    def log_message(self, *a):  # silence
        pass

    def _send_error(self, code: int, msg: str, extra: dict | None = None) -> None:
        body = json.dumps({"error": {"message": msg, "type": "gruntly_proxy", **(extra or {})}}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _forward(self, method: str) -> None:
        n = int(self.headers.get("Content-Length") or 0)
        body = dedupe_keys(self.rfile.read(n)) if n and method == "POST" else (self.rfile.read(n) if n else b"")
        srv = self.server
        path = self.path.split("?", 1)[0]
        if path.startswith("/v1"):
            path = path[3:]                           # the client's base URL ends in /v1; the provider's base has its own
        if method == "POST" and not srv.limiter.acquire(int(len(body) / TOKEN_CHARS) + 1):
            return self._send_error(429, f"daily request quota for {srv.name} is used up (limit {srv.limiter.rpd}/day, "
                                         "resets midnight Pacific). Try again tomorrow or use another provider.",
                                    {"code": "daily_quota"})
        u = urlparse(srv.upstream)
        for attempt in range(MAX_RETRIES + 4):
            conn = http.client.HTTPSConnection(u.netloc, timeout=600) if u.scheme == "https" else http.client.HTTPConnection(u.netloc, timeout=600)
            try:
                conn.request(method, u.path.rstrip("/") + path, body=body or None, headers={
                    "Authorization": f"Bearer {srv.key}", "Content-Type": self.headers.get("Content-Type", "application/json"),
                    "Accept": self.headers.get("Accept", "*/*")})
                r = conn.getresponse()
            except OSError as e:
                return self._send_error(502, f"upstream unreachable: {e}")
            if r.status in RETRY_5XX and attempt < MAX_RETRIES + 3:       # Gemma on the Gemini API answers 500 about half the time
                r.read()
                conn.close()
                srv.limiter.stats["retries_5xx"] += 1
                if srv.limiter.on_wait:
                    srv.limiter.on_wait(min(2 * (attempt + 1), 10), "provider error, retrying")
                srv.limiter.sleep(min(2 * (attempt + 1), 10))
                continue
            if r.status == 429 and attempt < MAX_RETRIES:
                data = r.read()
                wait = retry_after(r.headers, data)
                conn.close()
                if wait > MAX_WAIT_S:
                    self.send_response(429)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                srv.limiter.stats["retries_429"] += 1
                srv.limiter.stats["waited_s"] += wait
                if srv.limiter.on_wait:
                    srv.limiter.on_wait(round(wait), "provider asked to slow down")
                srv.limiter.sleep(wait + 0.5)
                continue
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() not in ("transfer-encoding", "connection", "content-length", "content-encoding"):
                    self.send_header(k, v)
            self.end_headers()
            try:
                while True:
                    chunk = r.read1(8192) if hasattr(r, "read1") else r.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except OSError:
                pass
            finally:
                conn.close()
            return

    def do_POST(self):
        self._forward("POST")

    def do_GET(self):
        self._forward("GET")


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, name: str, upstream: str, key: str, limiter: Limiter):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.name, self.upstream, self.key, self.limiter = name, upstream, key, limiter

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/v1"

    def stop(self) -> dict:
        self.shutdown()
        self.server_close()
        return dict(self.limiter.stats, waited_s=round(self.limiter.stats["waited_s"], 1))


def start(name: str, upstream: str, key: str, limits: dict, state: Path | None = None) -> ProxyServer:
    lim = Limiter(limits.get("rpm"), limits.get("tpm"), limits.get("rpd"), state)
    srv = ProxyServer(name, upstream, key, lim)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
