import builtins
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from gruntly import cli, keys, models, onboard, providers, settings_file


class Api(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/v1beta/models"):
            body = {"models": [{"name": "models/g-big", "displayName": "G Big", "description": "the big one",
                                "inputTokenLimit": 1000, "outputTokenLimit": 50, "thinking": True},
                               {"name": "models/g-small", "displayName": "G Small", "description": "G Small", "inputTokenLimit": 500}]}
        elif self.path.endswith("/models"):
            body = {"data": [{"id": "vendor/alpha", "owned_by": "vendor", "created": 735790403},
                             {"id": "vendor/beta", "owned_by": "vendor", "created": 1_760_000_000}]}
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("FAKEKEY", raising=False)
    monkeypatch.delenv("FAKEKEY2", raising=False)
    srv = HTTPServer(("127.0.0.1", 0), Api)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setattr(providers, "PROVIDERS", {
        "fakeg": providers.Provider("fakeg", base + "/v1beta/openai", "FAKEKEY", "g-small", models_api="gemini",
                                    docs=(("Get a key", "https://example.test/key"),)),
        "fakeo": providers.Provider("fakeo", base + "/v1", "FAKEKEY2", "vendor/alpha",
                                    docs=(("Models", "https://example.test/models"),))})
    keys.set_key("fakeg", "k1")
    keys.set_key("fakeo", "k2")
    yield base
    srv.shutdown()
    srv.server_close()


def test_the_gemini_style_listing_keeps_every_fact_the_endpoint_gives(api):
    ms = models.fetch("fakeg")
    assert [m.id for m in ms] == ["g-big", "g-small"]              # the models/ prefix is dropped
    big = ms[0]
    assert big.context == 1000 and big.info["about"] == "the big one" and big.info["max output"] == 50 and big.info["thinking"]
    assert "about" not in ms[1].info and ms[0].raw["displayName"] == "G Big"


def test_the_openai_style_listing_hides_a_bogus_date_but_keeps_it_in_raw(api):
    a, b = models.fetch("fakeo")
    assert "created" not in a.info and a.raw["created"] == 735790403
    assert b.info["created"].startswith("2025") and a.info["owner"] == "vendor"


def test_a_missing_key_or_server_is_a_clear_error(api, monkeypatch):
    monkeypatch.setattr(models, "_lms_exe", lambda: None)           # a real LM Studio on the machine would answer
    keys.remove("fakeo")
    with pytest.raises(models.ModelsError, match="gruntly auth set fakeo"):
        models.fetch("fakeo")
    with pytest.raises(models.ModelsError, match="could not reach"):
        models.fetch("local", "http://127.0.0.1:9/v1")


def test_set_values_edits_keys_and_keeps_everything_else(tmp_path):
    p = tmp_path / ".gruntly.toml"
    p.write_text('# my settings\nharness = "opencode"\nmodel = "old"\nbudget_s = 900\n\n[gates]\nlint = "ruff"\n', encoding="utf8")
    settings_file.set_values(p, {"provider": "gemini", "model": "new/one", "harness": None})
    text = p.read_text(encoding="utf8")
    assert 'provider = "gemini"' in text and 'model = "new/one"' in text and "harness" not in text and "old" not in text
    assert text.startswith("# my settings") and "budget_s = 900" in text and '[gates]\nlint = "ruff"' in text
    assert text.index("provider") < text.index("[gates]")           # keys stay above the first table
    assert settings_file.get_value(p, "model") == "new/one"
    settings_file.set_values(p, {"model": None})
    assert settings_file.get_value(p, "model") is None


def test_use_with_arguments_saves_the_choice_and_prints_the_docs(api, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert cli.main(["use", "fakeo", "vendor/beta", "--project"]) == 0
    out = capsys.readouterr().out
    assert "provider = fakeo, model = vendor/beta" in out and "https://example.test/models" in out
    cfg = repo / ".gruntly.toml"
    assert settings_file.get_value(cfg, "provider") == "fakeo" and settings_file.get_value(cfg, "model") == "vendor/beta"
    assert cli.main(["use", "fakeo", "not-a-model", "--project"]) == 0
    assert "not in the list" in capsys.readouterr().out
    assert cli.main(["use", "nope", "x"]) == 2


def test_use_back_to_local_removes_the_hosted_settings(api, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    cli.main(["use", "fakeo", "vendor/beta", "--project"])
    assert cli.main(["use", "local", "--project"]) == 0
    cfg = repo / ".gruntly.toml"
    assert settings_file.get_value(cfg, "provider") is None and settings_file.get_value(cfg, "model") is None


def test_models_command_lists_json_and_filters(api, capsys):
    assert cli.main(["models", "fakeo", "--filter", "beta"]) == 0
    out = capsys.readouterr().out
    assert "vendor/beta" in out and "vendor/alpha" not in out and "https://example.test/models" in out
    assert cli.main(["models", "fakeg", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["fakeg"][0]["displayName"] == "G Big"


def script(monkeypatch, answers, secret="typed-key"):
    it = iter(answers)
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(it))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": secret)
    monkeypatch.setattr(onboard, "interactive", lambda: True)


def test_the_picker_chooses_provider_then_model_by_filter_then_number(api, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    script(monkeypatch, ["3", "beta", "1", "p"])        # provider 3 = fakeo; filter "beta"; pick match 1; scope project
    assert cli.main(["use"]) == 0
    out = capsys.readouterr().out
    assert "1 match 'beta'" in out and "https://example.test/models" in out
    cfg = repo / ".gruntly.toml"
    assert settings_file.get_value(cfg, "provider") == "fakeo" and settings_file.get_value(cfg, "model") == "vendor/beta"


def test_a_provider_without_a_key_asks_for_one_and_never_echoes_it(api, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    keys.remove("fakeo")
    script(monkeypatch, ["3", "q", "p"], secret="SUPER-SECRET-KEY")
    cli.main(["use"])
    out = capsys.readouterr()
    assert "SUPER-SECRET-KEY" not in out.out + out.err
    assert keys.lookup("fakeo", "FAKEKEY2")[0] == "SUPER-SECRET-KEY"


def test_setup_walks_through_and_marks_the_person_as_onboarded(api, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert not onboard.is_onboarded()
    script(monkeypatch, ["3", "2", "p"])                # fakeo, its second model, this project
    assert cli.main(["setup"]) == 0
    out = capsys.readouterr().out
    assert "Step 1 of 3" in out and "Step 3 of 3" in out and "What gruntly does" in out and "gruntly agent-run --ask" in out
    assert "https://example.test/models" in out
    assert onboard.is_onboarded()
    assert settings_file.get_value(repo / ".gruntly.toml", "model") == "vendor/beta"


def test_first_run_offer_only_in_a_terminal_and_only_once(api, monkeypatch):
    monkeypatch.setattr(onboard, "interactive", lambda: False)
    assert onboard.first_run_offer() is False           # Claude calling gruntly is never interrupted
    script(monkeypatch, ["n"])
    assert onboard.first_run_offer() is True and onboard.is_onboarded()
    assert onboard.first_run_offer() is False


def test_auth_set_prints_where_to_get_a_key_and_what_next(api, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("some-key\n"))
    assert cli.main(["auth", "set", "fakeg"]) == 0
    out = capsys.readouterr().out
    assert "https://example.test/key" in out and "gruntly models fakeg" in out and "some-key" not in out


LMS_JSON = json.dumps([
    {"type": "llm", "modelKey": "qwen/qwen3.5-9b", "displayName": "Qwen3.5 9B", "paramsString": "9B", "architecture": "qwen35",
     "quantization": {"name": "Q4_K_M", "bits": 4}, "sizeBytes": 6_550_000_000, "trainedForToolUse": True, "maxContextLength": 262144},
    {"type": "embedding", "modelKey": "nomic", "displayName": "Nomic", "sizeBytes": 84_000_000, "maxContextLength": 2048}])


def test_downloaded_local_models_are_listed_without_the_server_running(monkeypatch):
    import subprocess
    monkeypatch.setattr(models, "_lms_exe", lambda: "lms")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=LMS_JSON, stderr=""))
    ms = models.fetch("local", "http://127.0.0.1:9/v1")              # nothing listens there: the server is off
    assert [m.id for m in ms] == ["qwen/qwen3.5-9b", "nomic"]
    q = ms[0]
    assert q.info["params"] == "9B" and q.info["quant"] == "Q4_K_M" and q.info["size"] == "6.5 GB" and q.info["tool use"]
    assert q.context == 262144 and ms[1].info["type"] == "embedding" and "state" not in q.info


def test_the_running_server_adds_which_model_is_loaded(monkeypatch):
    import subprocess
    monkeypatch.setattr(models, "_lms_exe", lambda: "lms")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=LMS_JSON, stderr=""))
    served = {"data": [{"id": "qwen/qwen3.5-9b", "state": "loaded", "loaded_context_length": 32768, "max_context_length": 262144}]}
    monkeypatch.setattr(models, "_get", lambda url, headers: served)
    q = models.fetch("local")[0]
    assert q.info["state"] == "loaded" and q.context == 32768


def test_without_lms_and_without_a_server_the_error_says_both(monkeypatch):
    monkeypatch.setattr(models, "_lms_exe", lambda: None)
    with pytest.raises(models.ModelsError, match="`lms` command was not found"):
        models.fetch("local", "http://127.0.0.1:9/v1")


def test_doctor_checks_the_hosted_provider_not_the_local_server(api, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    (repo / ".gruntly.toml").write_text('provider = "fakeo"\nmodel = "vendor/beta"\n', encoding="utf8")
    assert cli.main(["doctor"]) in (0, 1)
    out = json.loads(capsys.readouterr().out)
    checks = {c["check"]: c for c in out["checks"]}
    assert checks["model_server"]["ok"] and "not needed: this project uses fakeo" in checks["model_server"]["detail"]
    assert checks["provider_models:fakeo"]["ok"] and "2 models listed" in checks["provider_models:fakeo"]["detail"]
