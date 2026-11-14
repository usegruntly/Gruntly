"""When compacting a long conversation pays: the formula in gruntly/compaction.py, checked against the numbers measured on a real website chat
(47k tokens at its first turn, a summary of a few thousand, Sonnet 5.5's cache prices from gruntly's own table)."""
import json

import pytest

from gruntly import cli, compaction as cp, pricing


def sonnet():
    return pricing.price_for("anthropic", "claude-sonnet-5-5")


def test_the_formula_lands_on_the_defaults_for_sonnet_5_5():
    t = cp.thresholds(sonnet())
    assert t["source"] == "formula" and 94_000 <= t["soft"] <= 96_000 and 243_000 <= t["hard"] <= 245_000
    assert abs(t["soft"] - cp.DEFAULT_SOFT) < 6_000 and abs(t["hard"] - cp.DEFAULT_HARD) < 7_000      # the defaults were chosen first


def test_what_compacting_costs_and_when_it_pays_back():
    r = cp.rates(sonnet())
    assert cp.cost_to_compact(300_000, 5_000, r) == pytest.approx(0.10, abs=0.001)
    assert cp.saving_per_turn(300_000, 50_000, 5_000, r) == pytest.approx(0.0245, abs=0.0005)
    assert cp.break_even_turns(300_000, 50_000, 5_000, r) == pytest.approx(4.1, abs=0.2)
    assert cp.break_even_turns(500_000, 50_000, 5_000, r) < 3 < cp.break_even_turns(100_000, 50_000, 5_000, r)
    assert cp.break_even_turns(55_000, 50_000, 5_000, r) is None                  # nothing left to shed: never pays


def test_the_verdict_goes_from_dearer_to_equal_to_cheaper_as_the_context_grows():
    big = sonnet()
    assert cp.advice(80_000, 20, big)["verdict"] == "dearer to compact"
    assert cp.advice(94_800, 20, big)["verdict"] == "about equal"
    a = cp.advice(300_000, 20, big)
    assert a["verdict"] == "cheaper to compact" and a["saving_percent_of_carrying_on"] > 50
    assert cp.advice(300_000, 2, big)["verdict"] in ("dearer to compact", "about equal")         # a chat that is nearly over
    assert cp.advice(52_000, 20, big)["verdict"].startswith("never pays")


def test_without_a_price_nothing_is_guessed_and_the_defaults_stay():
    t = cp.thresholds(None)
    assert (t["soft"], t["hard"], t["source"]) == (cp.DEFAULT_SOFT, cp.DEFAULT_HARD, "default")
    a = cp.advice(300_000, 20, None)
    assert a["verdict"] == "unknown" and "compaction_cost" not in a


def test_a_model_without_cache_prices_rereads_at_its_plain_input_price():
    r = cp.rates(pricing.Price("x", "plain", 1.0, 4.0))
    assert r.read == pytest.approx(1e-6) and r.write == 0.0 and r.out == pytest.approx(4e-6)


def test_the_small_model_can_write_the_summary_only_if_it_is_cheaper_and_its_window_holds_the_conversation():
    big = sonnet()
    local_small_window = cp.advice(300_000, 20, big, None, small_local=True, small_window=32_768)["summary_by"]
    assert local_small_window["small_model"] == 0.0 and local_small_window["small_model_window_holds_it"] is False
    assert local_small_window["cheaper"].startswith("big model")
    local_big_window = cp.advice(300_000, 20, big, None, small_local=True, small_window=1_000_000)["summary_by"]
    assert local_big_window["cheaper"] == "small model"
    haiku = pricing.price_for("anthropic", "claude-haiku-5-5")
    assert cp.advice(300_000, 20, big, haiku, small_window=None)["summary_by"]["small_model_window_holds_it"] is None


def test_refresh_writes_the_thresholds_the_plugin_reads_and_only_when_they_change(repo):
    (repo / ".gruntly.toml").write_text('harness = "claude"\nmodel = "haiku"\n[parent]\nmodel = "claude-sonnet-5-5"\n')
    t = cp.refresh(repo)
    f = repo / ".gruntly" / "context.json"
    assert json.loads(f.read_text())["soft"] == t["soft"] and t["source"] == "formula" and t["parent_model"] == "claude-sonnet-5-5"
    stamp = f.stat().st_mtime_ns
    cp.refresh(repo)
    assert f.stat().st_mtime_ns == stamp
    (repo / ".gruntly.toml").write_text('[parent]\nmodel = "no-such-model"\n')
    assert cp.refresh(repo)["source"] == "default" and json.loads(f.read_text())["soft"] == cp.DEFAULT_SOFT


def test_the_context_command_prints_the_verdict_and_json(repo, capsys, monkeypatch):
    (repo / ".gruntly.toml").write_text('harness = "claude"\nmodel = "haiku"\n[parent]\nmodel = "claude-sonnet-5-5"\n')
    monkeypatch.chdir(repo)
    assert cli.main(["context", "--tokens", "300000", "--turns", "20", "--child-window", "1000000"]) == 0
    out = capsys.readouterr().out
    assert "claude-sonnet-5-5" in out and "cheaper to compact" in out and "claude-haiku-5-5" in out and "holds it" in out
    assert cli.main(["context", "--tokens", "80000", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["advice"]["verdict"] == "dearer to compact" and data["thresholds"]["source"] == "formula"
