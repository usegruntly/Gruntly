"""bench/delegation_export.py: a Claude child's cost is reproduced from `modelUsage`, whose cache-write split by TTL covers the whole session (the result event's
own `usage` only has the last turn's, which priced every write at the 1-hour rate and overshot the reported cost by 2.7%)."""
import importlib.util
import json
import sys
from pathlib import Path

BENCH = Path(__file__).parents[2] / "bench"
spec = importlib.util.spec_from_file_location("delegation_export", BENCH / "delegation_export.py")
de = importlib.util.module_from_spec(spec)
sys.modules["delegation_export"] = de
spec.loader.exec_module(de)

# A trimmed result line of a real Haiku child (bench/runs-agent/control_rfc6455_opcodes.forced.1.gruntly, 2026-11-12): the last turn wrote 6,968 tokens to the 1-hour cache and
# none to the 5-minute one, the whole session wrote 33,662 to the 5-minute cache and 6,968 to the 1-hour one.
RESULT = {"type": "result", "total_cost_usd": 0.014715579999999999, "num_turns": 2,
          "usage": {"input_tokens": 4, "cache_creation_input_tokens": 6968, "cache_read_input_tokens": 25762, "output_tokens": 922,
                    "cache_creation": {"ephemeral_1h_input_tokens": 6968, "ephemeral_5m_input_tokens": 0}},
          "modelUsage": {"claude-haiku-5-5": {"inputTokens": 62917, "outputTokens": 4680, "cacheReadInputTokens": 48253, "cacheCreationInputTokens": 40630, "webSearchRequests": 0,
                                              "costUSD": 0.014715579999999999, "cacheCreationEphemeral5mInputTokens": 33662, "cacheCreationEphemeral1hInputTokens": 6968}}}


def test_the_session_wide_ttl_split_reproduces_the_reported_cost_exactly(tmp_path):
    log = tmp_path / "child.log"
    log.write_text("=== attempt 1 exit=0 breach=none ===\n" + json.dumps(RESULT) + "\n", encoding="utf8")
    out = de.parse_child_log(log)
    model, a = next(iter(out["mu"].items()))
    assert (a[6], a[7]) == (33662, 6968)
    w5 = min(a[6], a[3]) if (a[6] + a[7]) else 0
    assert abs(de.price_call(model, a[0], a[1], a[2], w5, a[3] - w5) - RESULT["total_cost_usd"]) < 1e-9
    last_turn_only = de.price_call(model, a[0], a[1], a[2], out["w5"], a[3] - out["w5"])             # the old way: every write at the 1-hour rate
    assert last_turn_only > RESULT["total_cost_usd"] * 1.1


def test_the_defaults_point_into_the_repo():
    src = (BENCH / "delegation_export.py").read_text(encoding="utf8")
    assert 'repo / "docs" / "benchmarks" / "delegation-export"' in src and "Path(__file__).resolve().parent.parent" in src
