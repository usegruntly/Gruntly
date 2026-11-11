import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from gruntly import providers, proxy
from gruntly.proxy import Limiter


class Fake(BaseHTTPRequestHandler):
    seen: list = []
    fail_first = 0
    errors_first = 0

    def log_message(self, *a):
        pass

    def _reply(self, code, body, headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        Fake.seen.append((self.path, self.headers.get("Authorization"), self.rfile.read(n)))
        if Fake.errors_first > 0:
            Fake.errors_first -= 1
            return self._reply(500, b'{"error":{"status":"INTERNAL"}}')
        if Fake.fail_first > 0:
            Fake.fail_first -= 1
            return self._reply(429, b'{"error":"slow down"}', {"Retry-After": "0"})
        self._reply(200, b'{"choices":[{"message":{"content":"hi"}}]}', {"Content-Type": "application/json"})

    def do_GET(self):
        Fake.seen.append((self.path, self.headers.get("Authorization"), b""))
        self._reply(200, b'{"data":[{"id":"models/gemma-4-26b-a4b-it"}]}', {"Content-Type": "application/json"})


@pytest.fixture
def upstream():
    Fake.seen, Fake.fail_first, Fake.errors_first = [], 0, 0
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1beta/openai"
    srv.shutdown()
    srv.server_close()


def post(url, payload=None):
    req = urllib.request.Request(url + "/chat/completions", data=json.dumps(payload or {"m": 1}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer dummy"})
    return urllib.request.urlopen(req, timeout=20)


def test_the_proxy_adds_the_real_key_and_maps_the_path(upstream):
    srv = proxy.start("t", upstream, "REAL-KEY", {})
    try:
        assert json.load(post(srv.url))["choices"][0]["message"]["content"] == "hi"
        path, auth, _ = Fake.seen[0]
        assert path == "/v1beta/openai/chat/completions" and auth == "Bearer REAL-KEY"
        assert "models/gemma" in urllib.request.urlopen(srv.url + "/models", timeout=20).read().decode()
    finally:
        assert srv.stop()["requests"] == 1


def test_a_429_is_retried_after_the_delay_it_names(upstream):
    Fake.fail_first = 2
    srv = proxy.start("t", upstream, "k", {})
    srv.limiter.sleep = lambda s: None
    try:
        assert post(srv.url).status == 200
    finally:
        stats = srv.stop()
    assert stats["retries_429"] == 2 and len(Fake.seen) == 3


def test_the_daily_quota_stops_requests_with_a_clear_message(upstream, tmp_path):
    srv = proxy.start("t", upstream, "k", {"rpd": 1}, tmp_path / "day.json")
    try:
        post(srv.url)
        with pytest.raises(urllib.error.HTTPError) as e:
            post(srv.url)
        assert e.value.code == 429 and "daily request quota" in e.value.read().decode()
    finally:
        srv.stop()
    assert len(Fake.seen) == 1


def test_requests_per_minute_are_spaced_without_a_real_sleep():
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    lim = Limiter(rpm=2, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        assert lim.acquire(10)
    assert len(slept) == 1 and 59 < sum(slept) < 62     # the third request waits for the first to leave the window


def test_a_huge_request_still_goes_through_an_empty_window():
    lim = Limiter(tpm=1000, clock=lambda: 0.0, sleep=lambda s: None)
    assert lim.acquire(50_000)


def test_retry_after_reads_headers_and_bodies():
    assert proxy.retry_after({"Retry-After": "7"}, b"") == 7
    assert proxy.retry_after({}, b'{"retryDelay": "12s"}') == 12
    assert proxy.retry_after({}, b"Please retry in 3.5s") == 3.5
    assert proxy.retry_after({}, b"") == 20


def test_provider_presets_and_spec_validation():
    from gruntly.spec import SpecError, build_spec
    assert providers.get("gemini").default_model == "gemma-4-26b-a4b-it"
    assert build_spec({"brief": "x", "acceptance": ["true"], "provider": "gemini"}).provider == "gemini"
    with pytest.raises(SpecError):
        build_spec({"brief": "x", "acceptance": ["true"], "provider": "nope"})
    with pytest.raises(SpecError):
        build_spec({"brief": "x", "acceptance": ["true"], "provider": "gemini", "rate_limits": {"qps": 1}})


def test_a_run_without_the_api_key_says_which_variable_to_set(repo, make_spec, monkeypatch):
    from gruntly import runner, worktree
    from gruntly.spec import build_spec
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    root = worktree.preflight(repo)
    rid = runner.prepare(build_spec(make_spec("pass", provider="gemini"), root), root)
    res = runner.execute(root, rid)
    assert res["status"] == "error" and "GEMINI_API_KEY" in res["error"]


def test_a_500_from_the_provider_is_retried(upstream):
    Fake.errors_first = 2
    srv = proxy.start("t", upstream, "k", {})
    srv.limiter.sleep = lambda s: None
    try:
        assert post(srv.url).status == 200
    finally:
        stats = srv.stop()
    assert stats["retries_5xx"] == 2 and len(Fake.seen) == 3


def test_the_nvidia_preset_is_known_and_has_its_own_key_variable():
    p = providers.get("nvidia")
    assert p.base_url == "https://integrate.api.nvidia.com/v1" and p.key_env == "NVIDIA_API_KEY"
    from gruntly.spec import build_spec
    assert build_spec({"brief": "x", "acceptance": ["true"], "provider": "nvidia"}).provider == "nvidia"


def test_a_repeated_key_in_a_request_body_is_repaired_and_a_clean_body_is_untouched():
    from gruntly.proxy import dedupe_keys
    dup = b'{"messages":[{"role":"assistant","reasoning_content":"a","content":"x","reasoning_content":"b"}],"model":"m"}'
    fixed = json.loads(dedupe_keys(dup))
    assert fixed["messages"][0]["reasoning_content"] == "b" and fixed["model"] == "m"
    alias = json.loads(dedupe_keys(b'{"messages":[{"role":"assistant","reasoning":"a","reasoning_content":"a"}]}'))
    assert alias["messages"][0] == {"role": "assistant", "reasoning_content": "a"}   # `reasoning` is an alias upstream
    clean = b'{"model": "m",  "messages": []}'
    assert dedupe_keys(clean) is clean                      # same bytes, spacing included
    assert dedupe_keys(b"not json") == b"not json"




def test_a_field_a_model_refuses_is_dropped_for_that_provider_and_model_only():
    from gruntly.proxy import drop_rejected_fields
    body = b'{"model":"deepseek-ai/deepseek-v4.1-flash","reasoning_effort":"medium","messages":[]}'
    assert json.loads(drop_rejected_fields(body, "nvidia")) == {"model": "deepseek-ai/deepseek-v4.1-flash", "messages": []}
    other_model = b'{"model":"poolside/laguna-xs-2.1","reasoning_effort":"medium"}'
    assert drop_rejected_fields(other_model, "nvidia") is other_model             # Laguna takes it: untouched, same bytes
    assert drop_rejected_fields(body, "gemini") is body                           # another provider: untouched
    assert drop_rejected_fields(b"not json", "nvidia") == b"not json"
    assert drop_rejected_fields(b"[1]", "nvidia") == b"[1]"
