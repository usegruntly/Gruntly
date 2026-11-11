"""Cost of a delegated task against the parent doing it alone, by session regime, from measured parameters.

Everything here is derived from measured numbers (sources in docs/investigation-2026-11-11.md); the deep-session rows are a
model, not an end-to-end measurement. Prices are what Claude Code bills (verified against its own totals): Sonnet 5.5 input
$2/M, output $10/M, cache read $0.10/M, 1-hour cache write $4/M. Run: python bench/cost_model.py
"""
from __future__ import annotations

# ---- measured parameters -------------------------------------------------------------------------------------------
READ, WRITE, OUT = 0.10e-6, 4e-6, 10e-6          # Sonnet 5.5, $ per token
FRESH_TURN1 = 0.045                              # fresh `claude -p` session: 10.9k tokens of Claude Code's own prompt written to cache
FRESH_CTX = 27_000                               # context after turn 1 in the benchmark sessions
# median tokens a parent turn adds to the context while working alone (tool results, its own output), fresh benchmark
ALONE_NEW_PER_TURN = 700
# a delegation: the request (output) and the result block (written to the cache next turn)
REQUEST_OUT, BLOCK_TOKENS, REPLY_OUT = 150, 800, 120
HAIKU_CHILD = 0.005                              # Haiku 5.5 alone on a small task, measured mean $0.0045 (10 tasks), up to $0.009 on larger ones
SONNET_REVIEW = 0.0072                           # one Sonnet review, low effort, caching off, ~2k tokens in, ~300 out (measured)
HAIKU_REVIEW = 0.0006
# real-session per-turn medians (user's own transcripts): includes that turn's typical cache write
REGIMES = {"fresh benchmark session (27k)": None, "60-100k context": 0.0177, "100-150k": 0.0239, "150-300k": 0.0358, "300k+": 0.0759}


def turn_cost(ctx: int, new_tokens: int, out_tokens: int) -> float:
    return ctx * READ + new_tokens * WRITE + out_tokens * OUT


def alone(regime, turns: int) -> float:
    if REGIMES[regime] is None:
        c, ctx = FRESH_TURN1, FRESH_CTX
        for _ in range(turns - 1):
            c += turn_cost(ctx, ALONE_NEW_PER_TURN, 150)
            ctx += ALONE_NEW_PER_TURN
        return c
    return turns * REGIMES[regime]


def delegated(regime, parent_turns: int, child: float = 0.0, review: float = 0.0, takeover_p: float = 0.0, alone_turns: int = 4) -> float:
    """parent_turns: 2 (call + reply), 1 (the block arrives with the prompt, as /gd does), 0 (gruntly used outside the session)."""
    if REGIMES[regime] is None:
        c = FRESH_TURN1 if parent_turns else 0.0
        if parent_turns == 2:
            c += REQUEST_OUT * OUT + turn_cost(FRESH_CTX, BLOCK_TOKENS, REPLY_OUT)
        elif parent_turns == 1:
            c += turn_cost(FRESH_CTX, BLOCK_TOKENS, REPLY_OUT) - FRESH_CTX * READ   # the block is part of turn 1's write
    else:
        per = REGIMES[regime]
        c = parent_turns * per
    c += child + review
    return c + takeover_p * alone(regime, alone_turns)       # when the delegation fails, the parent does the task as well


def main() -> None:
    print("Measured check, fresh benchmark session, 4-turn task (Sonnet alone measured $0.062, delegated 2-turn measured $0.056):")
    print(f"  model: alone {alone('fresh benchmark session (27k)', 4):.3f}, delegated 2-turn {delegated('fresh benchmark session (27k)', 2):.3f}, "
          f"1-turn {delegated('fresh benchmark session (27k)', 1):.3f} (/gd measured $0.047)\n")
    designs = [
        ("Sonnet alone, 4 turns", lambda r: alone(r, 4)),
        ("Sonnet alone, 8 turns", lambda r: alone(r, 8)),
        ("gruntly, 2 parent turns, free child, gates only", lambda r: delegated(r, 2)),
        ("  + one Sonnet final review", lambda r: delegated(r, 2, review=SONNET_REVIEW)),
        ("  + 10% takeover risk (4-turn task)", lambda r: delegated(r, 2, review=SONNET_REVIEW, takeover_p=0.1)),
        ("gruntly, Haiku child in Claude Code, + Sonnet review", lambda r: delegated(r, 2, child=HAIKU_CHILD, review=SONNET_REVIEW)),
        ("supervised: 2 turns + plan review + 6 Haiku reviews + final Sonnet", lambda r: delegated(r, 2, review=2 * SONNET_REVIEW + 6 * HAIKU_REVIEW)),
        ("one parent turn (/gd style), free child, gates only", lambda r: delegated(r, 1)),
        ("gruntly outside the session + Sonnet review (0 parent turns)", lambda r: delegated(r, 0, review=SONNET_REVIEW)),
        ("Haiku alone in Claude Code (not a delegation)", lambda r: HAIKU_CHILD if REGIMES[r] is None else HAIKU_CHILD + 0.0),
    ]
    print(f"{'design':72} " + " ".join(f"{k[:14]:>14}" for k in REGIMES))
    for name, fn in designs:
        print(f"{name:72} " + " ".join(f"{fn(r):>14.3f}" for r in REGIMES))
    print("\nBreak-even: smallest number of alone turns the task must take for a 2-turn delegation (free child, one Sonnet review,")
    print("10% takeover) to cost less than Sonnet alone, by regime:")
    for r in REGIMES:
        t = next((n for n in range(2, 40) if delegated(r, 2, review=SONNET_REVIEW, takeover_p=0.1, alone_turns=n) < alone(r, n)), None)
        print(f"  {r:32} {t} turns" if t else f"  {r:32} never under 40 turns")
    print("\nContext growth kept out of the session per delegation (alone adds ~700 tokens a turn; the block adds ~800 once):")
    for turns in (4, 8, 15):
        kept = turns * ALONE_NEW_PER_TURN - BLOCK_TOKENS
        print(f"  {turns}-turn task: about {kept:,} tokens not added; worth ${kept * WRITE:.4f} at once plus ${kept * READ:.5f} on every later turn")


if __name__ == "__main__":
    main()
