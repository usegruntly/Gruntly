"""`gruntly models` shows what each model costs per token, for every option it lists: a price from gruntly's table or yours, the provider's own
listing price, free for a local server, and "unknown" (never zero) for anything gruntly has no price for."""
import json

import pytest

from gruntly import cli, models, pricing


def table():
    return pricing.load(user=False)


def test_a_packaged_claude_price_is_given_per_million_tokens_and_per_token():
    d = pricing.describe("anthropic", "claude-sonnet-5-5", table())
    assert d["status"] == "priced" and d["input_per_mtok"] == 2.0 and d["output_per_mtok"] == 10.0
    assert d["input_per_token"] == "0.000002" and d["output_per_token"] == "0.00001"
    assert pricing.describe_text(d) == "in $2 / out $10 per Mtok ($0.000002 / $0.00001 per token, gruntly's table)"


def test_a_providers_own_listing_price_is_used_and_zero_means_free():
    d = pricing.describe("openrouter", "some/model", table(), {"prompt": "0.00000015", "completion": "0.0000006"})
    assert d["status"] == "priced" and d["input_per_mtok"] == pytest.approx(0.15) and d["output_per_mtok"] == pytest.approx(0.6)
    assert d["source"] == "model listing" and pricing.describe_text(d).endswith("listing)")
    free = pricing.describe("openrouter", "free/model", table(), {"prompt": "0", "completion": "0"})
    assert free["status"] == "free" and pricing.describe_text(free).startswith("free ($0")


def test_a_local_server_is_free_and_a_model_without_a_price_is_unknown_never_zero():
    local = pricing.describe("local", "qwen3-9b", table(), local=True)
    assert local["status"] == "free" and pricing.describe_text(local) == "free (your own compute)"
    unknown = pricing.describe("groq", "some-model", table())
    assert unknown["status"] == "unknown" and "input_per_mtok" not in unknown and pricing.describe_text(unknown) == "price unknown"


def test_your_own_prices_file_decides_before_the_packaged_table():
    mine = [pricing.Price("anthropic", "claude-sonnet-*", 1.0, 5.0, None, None, "2026-11-14", "C:/me/prices.toml")]
    d = pricing.describe("anthropic", "claude-sonnet-5-5", mine)
    assert d["input_per_mtok"] == 1.0 and pricing.describe_text(d).endswith("your prices.toml)")


def test_a_model_line_says_the_price_once():
    m = models.Model("vendor/x", 8000, {"owner": "vendor", "price": "in $1 / out $2 per Mtok"})
    text = models.line(m, price="in $1 / out $2 per Mtok ($0.000001 / $0.000002 per token, listing)")
    assert text.count("per Mtok") == 1 and "owner: vendor" in text and text.endswith("listing)")
    assert "price:" in models.line(m)                               # without a computed price the listing's own fact still shows


def test_gruntly_models_anthropic_lists_claude_with_prices_and_json_carries_them(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path))
    assert cli.main(["models", "anthropic"]) == 0
    out = capsys.readouterr().out
    assert "claude-sonnet-5-5" in out and "in $2 / out $10 per Mtok" in out and "claude-haiku-5-5" in out and "claude-opus-5-5" in out
    assert cli.main(["models", "anthropic", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {r["gruntly_price"]["status"] for r in data["anthropic"]} == {"priced"}
    assert cli.main(["models", "nonesuch"]) == 2
