"""Usage parsing, the meter in the proxy, prices that are never silently zero, and the child's record."""
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from gruntly import accounting, models, pricing, proxy
from gruntly.usage import Meter, Sniffer, Usage, parse_body, parse_usage


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "cfg").mkdir()
    return tmp_path / "cfg"


def test_openai_shaped_usage_with_cache_reasoning_and_a_reported_cost():
    u = parse_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 30, "prompt_tokens_details": {"cached_tokens": 40},
                               "completion_tokens_details": {"reasoning_tokens": 12}, "cost": 0.00123}})
    assert (u.prompt, u.completion, u.cached, u.reasoning, u.cost_usd, u.total) == (100, 30, 40, 12, 0.00123, 130)
    assert parse_usage({"usage": {"prompt_tokens": 5, "completion_tokens": 1, "prompt_cache_hit_tokens": 3}}).cached == 3        # DeepSeek's name


def test_anthropic_shaped_usage_counts_cache_reads_and_writes_as_input():
    u = parse_usage({"usage": {"input_tokens": 10, "output_tokens": 6044, "cache_read_input_tokens": 152298, "cache_creation_input_tokens": 36098}})
    assert (u.prompt, u.completion, u.cached, u.cache_write) == (188406, 6044, 152298, 36098)


@pytest.mark.parametrize("junk", [None, [], "x", {}, {"usage": None}, {"usage": {"nothing": 1}}, {"usage": {"prompt_tokens": "many"}}])
def test_nothing_recognisable_is_none_not_zero(junk):
    u = parse_usage(junk)
    assert u is None or (u.prompt, u.completion) == (0, 0)                      # a non-number is never read as a count
    assert parse_usage({"usage": {"nothing": 1}}) is None


def test_a_plain_json_body_and_a_stream_are_both_read():
    assert parse_body(json.dumps({"usage": {"prompt_tokens": 7, "completion_tokens": 2}}).encode()).total == 9
    sse = (b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
           b'data: {"choices":[],"usage":{"prompt_tokens":20,"completion_tokens":4}}\n\ndata: [DONE]\n\n')
    assert parse_body(sse, "text/event-stream").total == 24
    anth = (b'event: message_start\ndata: {"message":{"usage":{"input_tokens":50,"output_tokens":1}}}\n\n'
            b'event: message_delta\ndata: {"usage":{"output_tokens":33}}\n\n')
    u = parse_body(anth, "text/event-stream")
    assert (u.prompt, u.completion) == (50, 33)                                    # input from the start, the larger output from the end
    assert parse_body(b"data: not json\n\ndata: [DONE]\n", "text/event-stream") is None and parse_body(b"<html>", "text/html") is None


def test_a_long_stream_is_read_from_its_head_and_tail_without_being_kept():
    s = Sniffer("text/event-stream")
    s.feed(b'data: {"message":{"usage":{"input_tokens":500,"output_tokens":1}}}\n\n')
    for _ in range(300):
        s.feed(b'data: {"choices":[{"delta":{"content":"' + b"x" * 1000 + b'"}}]}\n\n')
    s.feed(b'data: {"usage":{"output_tokens":777}}\n\ndata: [DONE]\n\n')
    u = s.usage()
    assert (u.prompt, u.completion) == (500, 777) and len(s.head) <= 16 * 1024 and len(s.tail) <= 80 * 1024 + 1


def test_the_meter_counts_a_response_without_usage_as_missing_not_zero():
    m = Meter()
    a = Sniffer("application/json")
    a.feed(json.dumps({"usage": {"prompt_tokens": 10, "completion_tokens": 2}}).encode())
    b = Sniffer("application/json")
    b.feed(b'{"choices": []}')
    m.record(a)
    m.record(b)
    snap = m.snapshot()
    assert snap["requests"] == 2 and snap["missing"] == 1 and snap["prompt"] == 10 and Usage.from_dict(snap).seen


def test_local_is_free_a_reported_cost_wins_and_an_unknown_price_is_unknown_not_zero(cfg):
    u = Usage(prompt=1000, completion=100, requests=1)
    assert pricing.cost(u, "ollama", "m", "local").usd == 0.0 and "not priced" in pricing.cost(u, "ollama", "m", "local").detail
    assert pricing.cost(Usage(prompt=1, completion=1, cost_usd=0.0042, requests=1), "openrouter", "x/y").usd == 0.0042
    c = pricing.cost(u, "groq", "some-model")
    assert c.usd is None and c.source == "unknown" and "prices.toml" in c.detail
    none_seen = Usage(requests=3, missing=3)
    assert pricing.cost(none_seen, "anthropic", "claude-haiku-5-5").usd is None and "no usage" in pricing.cost(none_seen, "anthropic", "claude-haiku-5-5").detail


def test_the_packaged_claude_prices_reproduce_claude_codes_own_cost():
    u = Usage(prompt=10 + 152298 + 36098, completion=6044, cached=152298, cache_write=36098, requests=1)
    assert pricing.cost(u, "anthropic", "claude-haiku-5-5").usd == pytest.approx(0.01176558, abs=2e-6)           # a recorded Haiku child run


def test_a_user_price_file_beats_the_table_and_a_project_file_beats_a_user_file(cfg, tmp_path):
    (cfg / "prices.toml").write_text('[[price]]\nprovider = "groq"\nmodel = "llama-*"\ninput = 0.5\noutput = 1.0\ncache_read = 0.05\nas_of = "2026-11-14"\n')
    u = Usage(prompt=1_000_000, completion=1_000_000, cached=400_000, requests=1)
    c = pricing.cost(u, "groq", "llama-3.3-70b")
    assert c.usd == pytest.approx(0.6 * 0.5 + 0.4 * 0.05 + 1.0) and c.source == "price table" and "as of 2026-11-14" in c.detail
    proj = tmp_path / "proj"
    (proj / ".gruntly").mkdir(parents=True)
    (proj / ".gruntly" / "prices.toml").write_text('[[price]]\nprovider = "groq"\nmodel = "llama-3.3-70b"\ninput = 2.0\noutput = 2.0\n')
    assert pricing.cost(u, "groq", "llama-3.3-70b", root=proj).usd == pytest.approx(4.0)       # 1M input (cached ones at the input price too) + 1M output, both $2
    assert pricing.price_for("groq", "llama-3.3-70b", proj).input == 2.0 and pricing.price_for("groq", "llama-3.3-70b").input == 0.5
    assert u.missing == 0 and "lower bound" in pricing.cost(Usage(prompt=1, completion=1, requests=2, missing=1), "groq", "llama-3.3-70b").detail


def test_a_broken_price_file_is_an_error_but_never_removes_the_packaged_prices(cfg):
    (cfg / "prices.toml").write_text('[[price]]\nprovider = "x"\n')
    with pytest.raises(pricing.PriceError, match="needs model"):
        pricing.load()
    assert pricing.price_for("anthropic", "claude-haiku-5-5").input == 0.10


def test_a_price_from_the_providers_own_listing_is_used_last(cfg):
    path = models.cache_path("openrouter")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ts": 1, "models": [{"id": "a/b", "raw": {"pricing": {"prompt": "0.000001", "completion": "0.000002"}}}]}))
    c = pricing.cost(Usage(prompt=1_000_000, completion=500_000, requests=1), "openrouter", "a/b")
    assert c.usd == pytest.approx(1.0 + 1.0) and c.source == "model listing"
    assert pricing.cost(Usage(prompt=1, completion=1, requests=1), "openrouter", "not/listed").usd is None


class Upstream(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        kind = body.get("kind")
        if kind == "stream":
            data = (b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
                    b'data: {"choices":[],"usage":{"prompt_tokens":30,"completion_tokens":5}}\n\ndata: [DONE]\n\n')
            ctype, code = "text/event-stream", 200
        elif kind == "nousage":
            data, ctype, code = b'{"choices":[{"message":{"content":"hi"}}]}', "application/json", 200
        elif kind == "fail":
            data, ctype, code = b'{"error":"nope"}', "application/json", 400
        else:
            data, ctype, code = json.dumps({"usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.0001}}).encode(), "application/json", 200
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def upstream():
    srv = HTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()
    srv.server_close()


def ask(url, kind):
    req = urllib.request.Request(url + "/chat/completions", data=json.dumps({"kind": kind}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer dummy"})
    try:
        return urllib.request.urlopen(req, timeout=20).read()
    except urllib.error.HTTPError as e:
        return e.read()


def test_the_proxy_meters_json_and_streamed_responses_and_counts_a_silent_one_as_missing(upstream):
    srv = proxy.start("fake", upstream, "real-key", {})
    try:
        ask(srv.url, "json")
        ask(srv.url, "stream")
        ask(srv.url, "nousage")
        ask(srv.url, "fail")                                              # an error response is not a counted request
    finally:
        snap = srv.stop()["usage"]
    assert snap["requests"] == 3 and snap["missing"] == 1 and snap["prompt"] == 40 and snap["completion"] == 7
    assert snap["cost_usd"] == pytest.approx(0.0001)


class FakeStore:
    def __init__(self):
        self.files = {}

    def read_json(self, name, default=None):
        return json.loads(json.dumps(self.files[name])) if name in self.files else default

    def write_json(self, name, data):
        self.files[name] = json.loads(json.dumps(data))


def test_finalizing_writes_tokens_and_dollars_and_adds_rounds_together(cfg):
    (cfg / "prices.toml").write_text('[[price]]\nprovider = "groq"\nmodel = "m1"\ninput = 1.0\noutput = 2.0\n')
    st = FakeStore()
    snap = Usage(prompt=1_000_000, completion=500_000, requests=4).to_dict()
    cu = accounting.finalize_child_usage(st, "groq", "m1", snap)
    assert cu["tokens"] == 1_500_000 and cu["requests"] == 4 and cu["cost_usd"] == pytest.approx(2.0) and cu["cost_source"] == "price table"
    assert "cost_unknown" not in cu
    cu = accounting.finalize_child_usage(st, "groq", "m1", Usage(prompt=1_000_000, completion=0, requests=1).to_dict())      # a follow-up round
    assert cu["proxy"]["usage"]["prompt"] == 2_000_000 and cu["cost_usd"] == pytest.approx(3.0)


def test_an_unpriced_hosted_child_is_marked_unknown_and_keeps_its_tokens(cfg):
    st = FakeStore()
    cu = accounting.finalize_child_usage(st, "groq", "no-price", Usage(prompt=100, completion=10, requests=2).to_dict())
    assert cu["cost_unknown"] is True and "cost_usd" not in cu and cu["tokens"] == 110 and cu["cost_source"] == "unknown"
    assert accounting.finalize_child_usage(FakeStore(), "groq", "no-price", Usage().to_dict()).get("cost_unknown") is None      # no requests: nothing unknown


def test_the_benchmark_report_names_the_runs_whose_child_price_is_unknown():
    import importlib.util
    import sys
    from pathlib import Path
    bench = Path(__file__).parents[2] / "bench"
    sys.path.insert(0, str(bench))
    spec = importlib.util.spec_from_file_location("rb_acct", bench / "run_bench.py")
    rb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rb)
    row = {"task": "t1", "bucket": "S", "arm": "forced", "rep": 1, "passed": True, "cost_usd": 0.05, "child_cost_usd": 0.0, "reviewer_cost_usd": 0, "turns": 2,
           "wall_s": 30, "tokens": {"output": 100}, "tool_output_bytes": 100, "gruntly_status": ["passed"], "gruntly_applied": [True], "gruntly_attempts": [1],
           "child_tokens": 100, "child_cost_unknown": 1, "takeover_edits": 0, "sessions": 1}
    text = rb.report([row], {"harness": "opencode", "model": "m", "parent_model": "sonnet"})
    assert "Child price unknown: 1 run(s)" in text and "t1/forced#1" in text and "lower bounds" in text
