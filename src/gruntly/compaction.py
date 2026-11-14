"""When is compacting a long conversation cheaper than carrying on?

Every turn of the big agent re-reads the whole conversation (a cache read: cheap per token, but it is paid again on EVERY turn). Compacting
replaces the conversation with a short summary, which costs something once and then makes every later turn cheaper. Whether that pays depends
on four things the price table and the model listing already know:

    C   the context now, in tokens (what each turn re-reads)
    B   what a compaction keeps whatever happens: system prompt, tools, skills, memory (about 50k in a real chat)
    S   what the summary takes (about 5k)
    N   how many more turns the chat will have
    r   cache read price per token of the big model;  w  its cache write price;  o  its output price

    cost of compacting once     = C*r  (the summariser reads the conversation)  +  S*o  (it writes the summary)  +  S*w  (the summary is written to the cache)
    saved on each later turn    = (C - B - S) * r
    pays back after             = cost / saved   turns
    worth it when               N * (C - B - S) * r  >=  C*r + S*(o + w)
    smallest context that pays  = (N*(B+S)*r + S*(o+w)) / ((N-1)*r)       (for N > 1)

With Sonnet 5.5's table prices ($0.10 read, $4 write, $10 output per Mtok) that gives 95k tokens for N=20 and 244k for N=5: the defaults below
(100k and 250k) were chosen first, and the formula lands on them. Where a price is missing the defaults stay: nothing here invents a price.

The summary can be written by the small model instead of the big one. That is cheaper only when its price is known (a local server is free)
AND its context window holds the whole conversation: a 32k local model cannot summarise 300k tokens. `advice` says which route is cheaper;
it does not switch routes by itself.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import pricing

BASE_TOKENS = 50_000        # measured: the website chat's context at its first turn was 47k
SUMMARY_TOKENS = 5_000
# Three plain messages, no numbers for the person to keep track of. Each level starts where compacting pays for itself within this many turns:
# 1 "suggested" (a long chat: if you can compact, fine), 2 "a good moment" (the usual case: 10 was the 25th percentile of the turns left in
# chats that had reached 50-100k, measured on 153 chats), 3 "please compact" (every turn now costs more than compacting would).
LEVEL_TURNS = (20, 10, 5)
DEFAULT_LEVELS = (100_000, 150_000, 250_000)      # where the three messages start for a model with no price: nothing is guessed
EQUAL_BAND = 0.10                       # within 10% of the compaction's own cost counts as "about equal"
ALIASES = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}     # names Claude Code's own child flag uses


@dataclass(frozen=True)
class Rates:
    read: float      # dollars per token, the context read from the cache
    write: float     # the context written to the cache
    out: float       # output


def rates(p: pricing.Price) -> Rates:
    """Per-token rates from a table price. A model with no cache prices re-reads at its plain input price and has no write premium."""
    read = (p.cache_read if p.cache_read is not None else p.input) / 1e6
    write = (p.cache_write if p.cache_write is not None else (p.input if p.cache_read is not None else 0.0)) / 1e6
    return Rates(read, write, p.output / 1e6)


def cost_to_compact(context: int, summary: int, r: Rates) -> float:
    return context * r.read + summary * (r.out + r.write)


def saving_per_turn(context: int, base: int, summary: int, r: Rates) -> float:
    return max(context - base - summary, 0) * r.read


def break_even_turns(context: int, base: int, summary: int, r: Rates) -> float | None:
    saved = saving_per_turn(context, base, summary, r)
    return cost_to_compact(context, summary, r) / saved if saved > 0 else None


def threshold(turns: int, base: int, summary: int, r: Rates) -> int | None:
    """The smallest context at which compacting pays back within `turns` more turns; None when it never can (turns <= 1 or reads are free)."""
    if turns <= 1 or r.read <= 0:
        return None
    return round((turns * (base + summary) * r.read + summary * (r.out + r.write)) / ((turns - 1) * r.read))


def thresholds(big: pricing.Price | None, base: int = BASE_TOKENS, summary: int = SUMMARY_TOKENS) -> dict:
    """Where the three messages start (`levels`, in tokens). From the formula when the big model's price is known, else the defaults."""
    if big is not None:
        r = rates(big)
        raw = [threshold(n, base, summary, r) for n in LEVEL_TURNS]
        if all(raw):
            first = max(raw[0], base + summary + 10_000)
            second = max(raw[1], first + 20_000)
            third = max(raw[2], second + 40_000)
            return {"levels": [first, second, third], "source": "formula",
                    "why": f"compacting pays for itself within {LEVEL_TURNS[0]}, {LEVEL_TURNS[1]} and {LEVEL_TURNS[2]} more turns above "
                           f"{first:,}, {second:,} and {third:,} tokens"}
    return {"levels": list(DEFAULT_LEVELS), "source": "default", "why": "no price for the big model, so the default levels stay"}


def advice(context: int, turns_left: int, big: pricing.Price | None, small: pricing.Price | None = None, small_local: bool = False,
           small_window: int | None = None, base: int = BASE_TOKENS, summary: int = SUMMARY_TOKENS) -> dict:
    """The verdict for a chat at `context` tokens that will have `turns_left` more turns."""
    out: dict = {"context": context, "turns_left": turns_left, "base": base, "summary": summary}
    if big is None:
        out.update(verdict="unknown", note="no price for the big model: use the default thresholds, nothing here is guessed")
        return out
    r = rates(big)
    cost, saved = cost_to_compact(context, summary, r), saving_per_turn(context, base, summary, r)
    net = turns_left * saved - cost
    carrying_on = turns_left * context * r.read
    out.update(compaction_cost=round(cost, 6), saved_per_turn=round(saved, 6), pays_back_after_turns=(round(cost / saved, 1) if saved else None),
               net_saving=round(net, 6), saving_percent_of_carrying_on=(round(100 * net / carrying_on, 1) if carrying_on else 0.0),
               smallest_context_that_pays=threshold(turns_left, base, summary, r))
    out["verdict"] = ("never pays (the context is no bigger than what a compaction keeps)" if saved <= 0 else
                      "about equal" if abs(net) <= EQUAL_BAND * cost else "cheaper to compact" if net > 0 else "dearer to compact")
    # who writes the summary: the big model (reads the conversation from its cache) or the small one (reads it as plain input)
    big_route = context * r.read + summary * r.out
    route: dict = {"big_model": round(big_route, 6)}
    if small_local:
        route["small_model"] = 0.0
    elif small is not None:
        route["small_model"] = round(context * small.input / 1e6 + summary * small.output / 1e6, 6)
    fits = None if small_window is None else small_window >= (context + summary) * 1.05
    route["small_model_window_holds_it"] = fits
    if "small_model" in route and fits:
        route["cheaper"] = "small model" if route["small_model"] < big_route else "big model"
    elif "small_model" in route and fits is False:
        route["cheaper"] = "big model (the small model's window is too small for this conversation)"
    out["summary_by"] = route
    return out


def project_models(root: Path | None) -> dict:
    """The big and small model of a project, from its settings: the [parent] table and the child's harness/model/provider."""
    from . import providers, spec
    cfg: dict = {}
    for p in (spec.global_config_path(), (Path(root) / ".gruntly.toml") if root else None):
        if p is not None:
            cfg = spec._merge(cfg, spec._toml(p))
    parent = (cfg.get("parent") or {}).get("model")
    harness, model, provider = cfg.get("harness"), cfg.get("model"), cfg.get("provider", "local")
    if harness == "claude":
        child_provider, child_model = "anthropic", ALIASES.get(str(model), model)
    else:
        child_provider, child_model = provider, model
    return {"parent_model": parent, "parent_provider": "anthropic" if str(parent or "").startswith("claude") else (cfg.get("parent") or {}).get("provider"),
            "child_model": child_model, "child_provider": child_provider,
            "child_local": harness != "claude" and (provider == "local" or provider in providers.LOCAL)}


def refresh(root: Path) -> dict:
    """Write `.gruntly/context.json` (the thresholds the Claude Code plugin reads) when it would change, and return what is in it."""
    m = project_models(root)
    big = pricing.price_for(m["parent_provider"], m["parent_model"], root) if m["parent_model"] and m["parent_provider"] else None
    t = thresholds(big)
    t["parent_model"] = m["parent_model"]
    f = Path(root) / ".gruntly" / "context.json"
    try:
        old = json.loads(f.read_text(encoding="utf8"))
    except (OSError, ValueError):
        old = None
    if old != t:
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(t, indent=2) + "\n", encoding="utf8")
        except OSError:
            pass                                       # a file that cannot be written only means the plugin uses its defaults
    return t
