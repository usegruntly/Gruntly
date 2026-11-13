"""The provider catalog: packaged data, user overrides, local servers, and that no key is ever printed."""
import json

import pytest

from gruntly import cli, providers
from gruntly.spec import build_spec

HOSTED = {"gemini", "nvidia", "openrouter", "openai", "deepseek", "groq", "together", "fireworks", "mistral", "cerebras", "xai"}
LOCAL = {"lmstudio", "ollama", "llamacpp", "vllm"}


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "cfg").mkdir()
    return tmp_path / "cfg"


def test_the_packaged_catalog_has_the_top_providers_and_the_local_servers():
    cat = providers.load(user=False)
    assert {n for n, p in cat.items() if p.kind == "hosted"} == HOSTED
    assert {n for n, p in cat.items() if p.kind == "local"} == LOCAL
    for n in HOSTED:
        p = cat[n]
        assert p.base_url.startswith("https://") and p.key_env.endswith("_API_KEY") and p.docs and all(len(d) == 2 for d in p.docs)
    for n in LOCAL:
        assert cat[n].base_url.startswith("http://127.0.0.1:") and cat[n].key_env == ""


def test_the_two_original_presets_are_unchanged():
    g, n = providers.load(user=False)["gemini"], providers.load(user=False)["nvidia"]
    assert (g.base_url, g.key_env, g.default_model, g.rpm, g.tpm, g.models_api, g.verified) == (
        "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemma-4-26b-a4b-it", 15, 15000, "gemini", True)
    assert (n.base_url, n.key_env, n.default_model, n.rpm, n.tpm, n.models_api, n.verified) == (
        "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", "nvidia/nemotron-3.5-bolt-e4b", 30, None, "openai", True)


def test_nothing_new_is_claimed_verified_and_no_model_id_is_hard_coded():
    cat = providers.load(user=False)
    assert {n for n, p in cat.items() if p.verified} == {"gemini", "nvidia", "openrouter"}  # only what a live check has passed (openrouter: 2026-11-13, `:free` models)
    assert all(p.default_model is None for n, p in cat.items() if n not in ("gemini", "nvidia"))


def test_a_later_file_overrides_field_by_field_and_a_project_file_wins_over_the_global_one(cfg, tmp_path):
    (cfg / "providers.toml").write_text('[groq]\nrpm = 20\n\n[mine]\nbase_url = "https://llm.example/v1"\nkey_env = "MINE_API_KEY"\n')
    proj = tmp_path / "proj"
    (proj / ".gruntly").mkdir(parents=True)
    (proj / ".gruntly" / "providers.toml").write_text('[groq]\nrpm = 5\nnote = "mine"\n')
    g = providers.load()
    assert g["groq"].rpm == 20 and g["groq"].base_url == "https://api.groq.com/openai/v1" and "mine" in g and g["mine"].kind == "hosted"
    p = providers.load(proj)
    assert p["groq"].rpm == 5 and p["groq"].note == "mine" and p["groq"].key_env == "GROQ_API_KEY"
    assert providers.get("groq", proj).rpm == 5 and providers.get("mine", proj).key_env == "MINE_API_KEY"


@pytest.mark.parametrize("body,fragment", [
    ('[x]\nbase_url = "https://a/v1"\nkey_env = "X_API_KEY"\nsurprise = 1\n', "unknown field"),
    ('[x]\nbase_url = "https://a/v1"\n', "needs key_env"),
    ('[x]\nkey_env = "X_API_KEY"\n', "needs a base_url"),
    ('[x]\nbase_url = "https://a/v1"\nkey_env = "X_API_KEY"\nrpm = "fast"\n', "whole number"),
    ('[x]\nbase_url = "https://a/v1"\nkey_env = "X_API_KEY"\nkind = "cloud"\n', "kind must be"),
    ('[x\nbroken', "providers.toml"),
])
def test_a_bad_user_file_is_an_error_that_names_the_file_and_the_field(cfg, body, fragment):
    (cfg / "providers.toml").write_text(body)
    with pytest.raises(providers.CatalogError) as e:
        providers.load()
    assert fragment in str(e.value) and "providers.toml" in str(e.value)


def test_a_broken_user_file_never_takes_the_packaged_catalog_down(cfg):
    (cfg / "providers.toml").write_text('[x]\nbase_url = "https://a/v1"\nbogus = 1\n')
    before = list(providers.LOAD_WARNINGS)
    try:
        cat = providers._initial()
        assert set(cat) >= HOSTED | LOCAL and "x" not in cat
        assert len(providers.LOAD_WARNINGS) == len(before) + 1 and "using the packaged catalog only" in providers.LOAD_WARNINGS[-1]
    finally:
        providers.LOAD_WARNINGS[:] = before


def test_a_local_server_name_means_the_local_provider_at_its_address():
    default = "http://127.0.0.1:1234/v1"
    assert providers.resolve_local("ollama", default, default) == ("local", "http://127.0.0.1:11434/v1")
    assert providers.resolve_local("vllm", None, default) == ("local", "http://127.0.0.1:8000/v1")
    assert providers.resolve_local("ollama", "http://10.0.0.5:11434/v1", default) == ("local", "http://10.0.0.5:11434/v1")   # an explicit endpoint wins
    assert providers.resolve_local("groq", default, default) == ("groq", default) and providers.resolve_local("local", default, default) == ("local", default)


def test_a_spec_can_name_a_local_server_or_a_hosted_provider(cfg):
    s = build_spec({"brief": "x", "acceptance": ["true"], "provider": "ollama"})
    assert s.provider == "local" and s.endpoint == "http://127.0.0.1:11434/v1"
    assert build_spec({"brief": "x", "acceptance": ["true"], "provider": "openrouter"}).provider == "openrouter"
    with pytest.raises(Exception, match="unknown provider"):
        build_spec({"brief": "x", "acceptance": ["true"], "provider": "nope"})


def test_unknown_provider_names_what_is_known():
    with pytest.raises(ValueError) as e:
        providers.get("nope")
    assert "known: local, gemini, nvidia, openrouter" in str(e.value)


def test_the_providers_command_shows_key_status_and_never_a_key(cfg, monkeypatch, capsys):
    secret = "sk-test-SECRET-1234567890"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert cli.main(["providers", "--json"]) == 0
    out = capsys.readouterr().out
    data = {r["name"]: r for r in json.loads(out)["providers"]}
    assert data["openrouter"]["key"] == "set" and data["groq"]["key"] == "missing" and data["ollama"]["key"] == "n/a"
    assert secret not in out
    assert cli.main(["providers"]) == 0
    text = capsys.readouterr().out
    assert secret not in text and "openrouter" in text and "(choose one)" in text and "verified = a live check has passed" in text


def test_a_hosted_provider_without_a_default_model_says_how_to_pick_one(run_task, make_spec, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-not-a-real-key")
    res, _ = run_task(make_spec("pass", provider="openrouter"))
    assert res["status"] == "error" and "has no default model" in res["error"] and "gruntly models openrouter" in res["error"]


def test_the_responses_api_flag_is_true_false_or_unknown_and_nothing_else():
    assert providers.ALL["openai"].responses_api is True and providers.ALL["deepseek"].responses_api is False and providers.ALL["mistral"].responses_api is None
    assert providers._build("x", {"base_url": "http://a", "kind": "local", "responses_api": True}, "t").responses_api is True
    with pytest.raises(providers.CatalogError, match="responses_api must be true or false"):
        providers._build("x", {"base_url": "http://a", "kind": "local", "responses_api": "yes"}, "t")
