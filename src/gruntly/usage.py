"""What a model call used, read from the provider's own response: prompt, completion and cached tokens, and a dollar figure when the
provider reports one (OpenRouter does).

Nothing here guesses. A response with no usage in it is counted as `missing`, not as zero, so a total built from it says so. Two wire
shapes are understood: the OpenAI one (`prompt_tokens`, `completion_tokens`, cached tokens under `prompt_tokens_details`) that
nearly every hosted provider speaks, and Anthropic's native one (`input_tokens`, `output_tokens`, cache reads and writes as separate
counts), which a direct-API parent needs. Streaming (server-sent events) is read from the head and the tail of the stream, where the
usage lives, so a long stream is never held in memory.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass

HEAD_BYTES = 16 * 1024
TAIL_BYTES = 64 * 1024
BODY_CAP = 4 * 1024 * 1024


@dataclass
class Usage:
    prompt: int = 0               # all input tokens, cached ones included (the OpenAI meaning)
    completion: int = 0
    cached: int = 0               # input tokens read from the provider's cache (usually cheaper)
    cache_write: int = 0          # input tokens written to a cache (Anthropic bills these separately)
    reasoning: int = 0            # part of completion; for information
    cost_usd: float | None = None  # a dollar figure the PROVIDER reported, never one we computed
    requests: int = 0
    missing: int = 0              # responses that carried no usage at all

    def add(self, o: "Usage") -> None:
        for f in ("prompt", "completion", "cached", "cache_write", "reasoning", "requests", "missing"):
            setattr(self, f, getattr(self, f) + getattr(o, f))
        if o.cost_usd is not None:
            self.cost_usd = (self.cost_usd or 0.0) + o.cost_usd

    @property
    def total(self) -> int:
        return self.prompt + self.completion

    @property
    def seen(self) -> bool:
        """Did any response carry usage? (A run with requests but no usage has unknown, not zero, tokens.)"""
        return self.requests > self.missing

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict | None) -> "Usage":
        d = d or {}
        return Usage(**{k: d[k] for k in ("prompt", "completion", "cached", "cache_write", "reasoning", "cost_usd", "requests", "missing") if k in d})


def _int(x) -> int:
    return x if isinstance(x, int) and not isinstance(x, bool) and x > 0 else 0


def parse_usage(d) -> Usage | None:
    """Usage from a response body (or from its `usage` object). None when there is nothing recognisable."""
    if not isinstance(d, dict):
        return None
    u = d.get("usage") if isinstance(d.get("usage"), dict) else (d.get("message", {}).get("usage") if isinstance(d.get("message"), dict) else None)
    if u is None and ("prompt_tokens" in d or "input_tokens" in d):
        u = d
    if not isinstance(u, dict):
        return None
    if "input_tokens" in u or "output_tokens" in u:           # Anthropic's native shape: cache reads and writes are separate counts
        read, write = _int(u.get("cache_read_input_tokens")), _int(u.get("cache_creation_input_tokens"))
        out = Usage(prompt=_int(u.get("input_tokens")) + read + write, completion=_int(u.get("output_tokens")), cached=read, cache_write=write)
    elif "prompt_tokens" in u or "completion_tokens" in u:     # the OpenAI shape
        details = u.get("prompt_tokens_details") if isinstance(u.get("prompt_tokens_details"), dict) else {}
        cdetails = u.get("completion_tokens_details") if isinstance(u.get("completion_tokens_details"), dict) else {}
        out = Usage(prompt=_int(u.get("prompt_tokens")), completion=_int(u.get("completion_tokens")),
                    cached=_int(details.get("cached_tokens")) or _int(u.get("prompt_cache_hit_tokens")), reasoning=_int(cdetails.get("reasoning_tokens")))
    else:
        return None
    c = u.get("cost")
    if isinstance(c, (int, float)) and not isinstance(c, bool) and c >= 0:
        out.cost_usd = float(c)
    return out


def _merge_max(a: Usage | None, b: Usage) -> Usage:
    """Streamed usage arrives in pieces (Anthropic: input first, output last) or once at the end (OpenAI): taking the larger of each count
    gives the right total for both without double counting."""
    if a is None:
        return b
    for f in ("prompt", "completion", "cached", "cache_write", "reasoning"):
        setattr(a, f, max(getattr(a, f), getattr(b, f)))
    if b.cost_usd is not None:
        a.cost_usd = max(a.cost_usd or 0.0, b.cost_usd)
    return a


def parse_body(raw: bytes, content_type: str = "") -> Usage | None:
    text = raw.decode("utf8", "replace")
    if "event-stream" in content_type.lower() or text.lstrip().startswith(("data:", "event:")):
        found = None
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                u = parse_usage(json.loads(payload))
            except ValueError:
                continue
            if u is not None:
                found = _merge_max(found, u)
        return found
    try:
        return parse_usage(json.loads(text))
    except ValueError:
        return None


class Sniffer:
    """Watches a response go by and keeps just enough of it: the head and the tail of a stream, or the whole of a small JSON body."""

    def __init__(self, content_type: str = ""):
        self.content_type = content_type
        self.head = bytearray()
        self.tail = bytearray()
        self.size = 0

    def feed(self, chunk: bytes) -> None:
        self.size += len(chunk)
        if len(self.head) < HEAD_BYTES:
            self.head += chunk[: HEAD_BYTES - len(self.head)]
        self.tail += chunk
        if len(self.tail) > TAIL_BYTES + HEAD_BYTES:
            del self.tail[: len(self.tail) - TAIL_BYTES]

    def usage(self) -> Usage | None:
        if "event-stream" not in self.content_type.lower() and self.size <= BODY_CAP and self.size <= HEAD_BYTES + TAIL_BYTES:
            return parse_body(bytes(self.tail if self.size > HEAD_BYTES else self.head), self.content_type)
        raw = bytes(self.head) + b"\n" + bytes(self.tail)           # a stream: its start and its end
        return parse_body(raw, self.content_type or "text/event-stream")


class Meter:
    """The usage of every response through one proxy, thread-safe. A response without usage counts as missing."""

    def __init__(self):
        self._u = Usage()
        self._lock = threading.Lock()

    def record(self, sniffer: Sniffer, ok: bool = True) -> None:
        u = sniffer.usage() if ok else None
        with self._lock:
            self._u.requests += 1
            if u is None:
                self._u.missing += 1
            else:
                self._u.add(Usage(u.prompt, u.completion, u.cached, u.cache_write, u.reasoning, u.cost_usd))

    def snapshot(self) -> dict:
        with self._lock:
            return self._u.to_dict()
