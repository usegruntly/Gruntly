"""gruntly verify and the day cache of model lists, against a fake OpenAI-compatible server (no network, no key)."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from gruntly import cli, models, providers, verify

KEY = "sk-fake-GOOD-1234567890"


class Fake:
    """A tiny OpenAI-compatible server: /v1/models and /v1/chat/completions, with behaviour chosen by the model name."""

    def __init__(self):
        outer = self
        self.hits = {"models": 0, "chat": 0}
        self.calls: dict[str, int] = {}
        self.auth_required = True

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _auth(self):
                got = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
                if outer.auth_required and got != KEY:
                    self._send(401, {"error": f"invalid api key: {got}"})          # some providers echo the key back
                    return False
                return True

            def do_GET(self):
                outer.hits["models"] += 1
                if self.path.endswith("/models") and self._auth():
                    self._send(200, {"data": [{"id": "good", "context_length": 32768, "pricing": {"prompt": "0.0000002", "completion": "0.0000006"}},
                                              {"id": "other"}]})

            def do_POST(self):
                outer.hits["chat"] += 1
                if not self._auth():
                    return
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                m = body["model"]
                outer.calls[m] = outer.calls.get(m, 0) + 1
                if m == "flaky" and outer.calls[m] == 1:
                    return self._send(500, {"error": "internal"})
                if m == "hangs-once" and outer.calls[m] == 1:
                    time.sleep(1.5)
                if m == "slow":
                    time.sleep(1.5)
                if m == "missing":
                    return self._send(404, {"error": "model not found"})
                if m == "limited":
                    return self._send(429, {"error": "slow down"})
                if m == "boom":
                    return self._send(500, {"error": "internal"})
                if m == "weird":
                    return self._send(200, {"nothing": True})
                self._send(200, {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10}})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}/v1"

    def stop(self):
        self.srv.shutdown()


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "RETRY_WAIT", (0.0, 0.0))                           # the retries are tested, the waiting between them is not
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("FAKE_API_KEY", KEY)
    f = Fake()
    yield f
    f.stop()


def prov(fake, **kw):
    d = dict(name="fake", base_url=fake.base, key_env="FAKE_API_KEY", default_model="good")
    d.update(kw)
    return providers.Provider(**d)


def test_a_working_provider_lists_models_and_answers_one_tiny_call(fake):
    c = verify.check(prov(fake))
    assert c.ok and c.stage == "chat" and c.models == 2 and c.model == "good" and c.usage["total_tokens"] == 10 and c.latency_ms is not None
    assert fake.hits == {"models": 1, "chat": 1} and "10 tokens" in c.detail


def test_no_key_is_a_skip_and_the_server_is_never_contacted(fake, monkeypatch):
    monkeypatch.delenv("FAKE_API_KEY")
    c = verify.check(prov(fake))
    assert (c.ok, c.stage, c.error) == (False, "skipped", "no_key") and "FAKE_API_KEY" in c.detail and fake.hits == {"models": 0, "chat": 0}


def test_a_bad_key_is_an_auth_error_and_the_key_is_never_in_the_message(fake, monkeypatch):
    wrong = "sk-wrong-SECRET-abcdef"
    monkeypatch.setenv("FAKE_API_KEY", wrong)
    c = verify.check(prov(fake))
    assert not c.ok and c.error == "auth" and c.stage == "models" and wrong not in c.detail and "HTTP 401" in c.detail


@pytest.mark.parametrize("model,error", [("missing", "not_found"), ("limited", "rate_limit"), ("boom", "server"), ("weird", "other")])
def test_each_failure_of_the_call_has_its_own_class(fake, model, error):
    c = verify.check(prov(fake), model=model)
    assert not c.ok and c.error == error and c.stage == "chat" and c.models == 2 and model in c.detail


def test_a_slow_answer_is_a_timeout(fake):
    c = verify.check(prov(fake), model="slow", timeout=0.4)
    assert not c.ok and c.error == "timeout"


def test_an_unreachable_server_is_a_network_error_and_a_local_one_says_it_is_not_running(fake):
    dead = "http://127.0.0.1:1/v1"                      # nothing listens on port 1
    assert verify.check(prov(fake, base_url=dead)).error == "network"
    local = verify.check(prov(fake, base_url=dead, kind="local", key_env=""), timeout=0.5)
    assert not local.ok and local.error == "network" and local.detail.startswith("not running")


def test_a_provider_without_a_default_model_only_checks_the_list(fake):
    c = verify.check(prov(fake, default_model=None))
    assert c.ok and c.stage == "models" and c.models == 2 and "--model" in c.detail and fake.hits["chat"] == 0


def test_the_default_sweep_takes_hosted_providers_with_a_key_and_every_local_server(fake, monkeypatch):
    cat = {"fake": prov(fake), "nokey": prov(fake, name="nokey", key_env="NOKEY_API_KEY"),
           "localdead": prov(fake, name="localdead", base_url="http://127.0.0.1:1/v1", kind="local", key_env="")}
    monkeypatch.delenv("NOKEY_API_KEY", raising=False)
    names = [c.provider for c in verify.run(catalog=cat)]
    assert names == ["fake", "localdead"]
    with pytest.raises(ValueError, match="unknown provider 'nope'"):
        verify.run(["nope"], catalog=cat)


def test_the_command_exit_code_and_output(fake, monkeypatch, capsys):
    cat = {"fake": prov(fake), "localdead": prov(fake, name="localdead", base_url="http://127.0.0.1:1/v1", kind="local", key_env="")}
    monkeypatch.setattr(providers, "ALL", cat)
    monkeypatch.setattr(verify, "LOCAL_TIMEOUT", 0.5)
    assert cli.main(["verify"]) == 0                                   # a local server that is off is not a failure of the sweep
    out = capsys.readouterr().out
    assert "fake" in out and "ok" in out and "not running" in out and "FAILED" not in out and KEY not in out   # an off local server reads "not running", not as a failure
    assert cli.main(["verify", "localdead"]) == 1                      # but naming it asks for it to work
    capsys.readouterr()
    assert cli.main(["verify", "fake", "--model", "limited", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data[0]["error"] == "rate_limit" and KEY not in json.dumps(data)
    assert cli.main(["verify", "nope"]) == 2


def test_the_last_result_is_kept_and_shown_by_providers(fake, monkeypatch, capsys):
    monkeypatch.setattr(providers, "ALL", {"fake": prov(fake)})
    verify.record([verify.check(prov(fake)), verify.Check("skipped-one", "hosted", False, "skipped", "no_key")], now=1_800_000_000)
    kept = verify.last_results()
    assert kept["fake"]["ok"] is True and "skipped-one" not in kept
    assert cli.main(["providers", "--json"]) == 0
    row = json.loads(capsys.readouterr().out)["providers"][0]
    assert row["checked_here"].startswith("ok 20")


def test_model_lists_carry_context_and_price_when_the_provider_gives_them(fake, monkeypatch):
    monkeypatch.setitem(providers.PROVIDERS, "fake", prov(fake))
    ms = models.fetch("fake")
    good = next(m for m in ms if m.id == "good")
    assert good.context == 32768 and good.info["price"] == "in $0.2 / out $0.6 per Mtok"


def test_a_hosted_list_is_cached_for_a_day_and_refresh_or_age_asks_again(fake, monkeypatch):
    monkeypatch.setitem(providers.PROVIDERS, "fake", prov(fake))
    t = 1_800_000_000.0
    ms, age = models.fetch_cached("fake", now=t)
    assert age is None and len(ms) == 2 and fake.hits["models"] == 1
    ms2, age2 = models.fetch_cached("fake", now=t + 3600)
    assert age2 == 3600 and fake.hits["models"] == 1 and [m.id for m in ms2] == ["good", "other"] and ms2[0].context == 32768
    assert models.fetch_cached("fake", refresh=True, now=t + 3700)[1] is None and fake.hits["models"] == 2
    assert models.fetch_cached("fake", now=t + 3700 + 2 * 86400)[1] is None and fake.hits["models"] == 3         # older than a day


def test_a_local_list_is_never_cached(fake, monkeypatch):
    fake.auth_required = False                                  # a local server wants no key
    monkeypatch.setitem(providers.LOCAL, "ollama", providers.Provider("ollama", fake.base, "", None, kind="local"))
    monkeypatch.setattr(models, "_lms_downloaded", lambda: None)
    _, age = models.fetch_cached("ollama")
    assert age is None and not models.cache_path("ollama").exists()


def test_a_transient_failure_is_retried_and_the_detail_says_so(fake):
    c = verify.check(prov(fake), model="flaky")                                      # HTTP 500 on the first call, fine on the second
    assert c.ok and c.tries == 2 and fake.calls["flaky"] == 2 and "on try 2 (earlier: server)" in c.detail
    h = verify.check(prov(fake), model="hangs-once", timeout=0.5)                    # the first call hangs past the timeout
    assert h.ok and h.tries == 2 and "earlier: timeout" in h.detail


def test_a_failure_that_does_not_clear_is_reported_after_all_the_tries_and_other_classes_are_not_retried(fake):
    c = verify.check(prov(fake), model="boom")
    assert not c.ok and c.error == "server" and c.tries == verify.RETRIES + 1 and fake.calls["boom"] == 3 and f"after {verify.RETRIES + 1} tries" in c.detail
    for model, error in (("missing", "not_found"), ("limited", "rate_limit")):       # a 404 or a 429 says something retrying will not change
        r = verify.check(prov(fake), model=model)
        assert r.error == error and r.tries == 1 and fake.calls[model] == 1


def test_a_missing_root_certificate_store_gets_its_own_class_with_the_fix(fake):
    import ssl
    import urllib.error
    cls, detail = verify.classify(urllib.error.URLError(ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate")))
    assert cls == "tls" and "Install Certificates.command" in detail and "SSL_CERT_FILE" in detail
    assert verify.classify(urllib.error.URLError(ConnectionRefusedError("refused")))[0] == "network"          # a refused connection is still just the network
    assert "tls" not in verify.RETRY_ON                                                                        # retrying cannot give Python a certificate store
