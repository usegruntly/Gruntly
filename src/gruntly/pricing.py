"""Dollars for a Usage: reported by the provider, from a price table, from the provider's model listing, or UNKNOWN (never zero).

Local servers cost nothing in API dollars and say so ("compute not priced"). Everything else that cannot be priced returns
`usd = None` with the reason, so a report can show "tokens, price unknown" instead of a total that quietly leaves it out.
"""
from __future__ import annotations

import fnmatch
import json
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .usage import Usage


class PriceError(ValueError):
    pass


@dataclass(frozen=True)
class Price:
    provider: str
    model: str
    input: float                   # $ per million prompt tokens
    output: float
    cache_read: float | None = None
    cache_write: float | None = None
    as_of: str = ""
    source: str = "price table"


@dataclass(frozen=True)
class Cost:
    usd: float | None
    source: str                    # reported by the provider | price table | model listing | local | unknown
    detail: str = ""


def _prices(text: str, where: str) -> list[Price]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise PriceError(f"{where}: {e}") from None
    out = []
    for i, t in enumerate(data.get("price", []), 1):
        for f in ("provider", "model", "input", "output"):
            if f not in t:
                raise PriceError(f"{where}: price #{i} needs {f}")
        for f in ("input", "output", "cache_read", "cache_write"):
            if f in t and (isinstance(t[f], bool) or not isinstance(t[f], (int, float)) or t[f] < 0):
                raise PriceError(f"{where}: price #{i} {f} must be a number of dollars per million tokens")
        out.append(Price(str(t["provider"]), str(t["model"]), float(t["input"]), float(t["output"]), t.get("cache_read"), t.get("cache_write"),
                         str(t.get("as_of", "")), where))
    return out


def user_files(root: Path | None = None) -> list[Path]:
    from .spec import global_config_path
    files = [global_config_path().parent / "prices.toml"]
    if root is not None:
        files.append(Path(root) / ".gruntly" / "prices.toml")
    return files


def load(root: Path | None = None, user: bool = True) -> list[Price]:
    """Most specific first: the project's file, then yours, then the packaged table."""
    tables = []
    for p in reversed(user_files(root)) if user else []:
        if p.is_file():
            tables.append(_prices(p.read_text(encoding="utf8"), str(p)))
    tables.append(_prices(resources.files("gruntly").joinpath("data/prices.toml").read_text(encoding="utf8"), "packaged prices.toml"))
    return [p for t in tables for p in t]


def _listing_price(provider: str, model: str) -> Price | None:
    """The price a provider's own model listing gives (OpenRouter, Together), from the cached `gruntly models` list. None when absent."""
    from . import models
    try:
        d = json.loads(models.cache_path(provider).read_text(encoding="utf8"))
    except (OSError, ValueError):
        return None
    for m in d.get("models", []):
        if m.get("id") == model:
            nums = models.price_numbers((m.get("raw") or {}).get("pricing"))
            if nums:
                return Price(provider, model, nums[0], nums[1], None, None, "", "model listing")
    return None


def per_token(per_mtok: float) -> str:
    """Dollars per million tokens as dollars per ONE token, written out in full (2.0 -> 0.000002)."""
    return f"{per_mtok / 1e6:.10f}".rstrip("0").rstrip(".") or "0"


def describe(provider: str, model: str, table: list[Price] | None = None, listing: dict | None = None, local: bool = False) -> dict:
    """What a model costs, for a listing of models: `status` is free (a local server, or a listing that says $0), priced (with the rates per
    million tokens and per token, and where the rate came from) or unknown. Never a made-up number: unknown stays unknown, as in `cost`.
    `table` is the loaded price table (load it once for a long list); `listing` is the model's own pricing object from the provider's listing."""
    from . import models
    if local:
        return {"status": "free", "note": "your own compute; gruntly does not price it"}
    rates = None
    for p in table if table is not None else load():
        if p.provider == provider and fnmatch.fnmatch(model, p.model):
            rates = (p.input, p.output, p.cache_read, p.cache_write, p.source, p.as_of)
            break
    if rates is None:
        nums = models.price_numbers(listing)
        if nums:
            rates = (nums[0], nums[1], None, None, "model listing", "")
    if rates is None:
        return {"status": "unknown", "note": f"no price for {provider}/{model}; add one to {user_files()[0]}"}
    i, o, cr, cw, source, as_of = rates
    out = {"status": "free" if i == 0 and o == 0 else "priced", "input_per_mtok": i, "output_per_mtok": o,
           "input_per_token": per_token(i), "output_per_token": per_token(o), "source": source, "as_of": as_of}
    if cr is not None:
        out["cache_read_per_mtok"] = cr
    if cw is not None:
        out["cache_write_per_mtok"] = cw
    return out


def describe_text(d: dict) -> str:
    """One short phrase for a model line."""
    if d["status"] == "unknown":
        return "price unknown"
    if d["status"] == "free" and "input_per_mtok" not in d:
        return "free (your own compute)"
    src = d.get("source", "")
    where = "listing" if src == "model listing" else "gruntly's table" if src.startswith("packaged") else "your prices.toml"
    if d["status"] == "free":
        return f"free ($0, {where})"
    return (f"in ${d['input_per_mtok']:g} / out ${d['output_per_mtok']:g} per Mtok "
            f"(${d['input_per_token']} / ${d['output_per_token']} per token, {where})")


def price_for(provider: str, model: str | None, root: Path | None = None) -> Price | None:
    if not model:
        return None
    try:
        table = load(root)
    except PriceError:
        table = load(user=False)           # a broken user file never takes the packaged prices down with it
    for p in table:
        if p.provider == provider and fnmatch.fnmatch(model, p.model):
            return p
    return _listing_price(provider, model)


def cost(usage: Usage, provider: str, model: str | None, kind: str = "hosted", root: Path | None = None) -> Cost:
    if kind == "local":
        return Cost(0.0, "local", "a local server costs no API dollars; compute is not priced")
    if usage.requests and not usage.seen:
        return Cost(None, "unknown", "the provider's responses carried no usage, so tokens and dollars are unknown")
    if usage.cost_usd is not None:
        return Cost(round(usage.cost_usd, 6), "reported by the provider")
    p = price_for(provider, model, root)
    if p is None:
        return Cost(None, "unknown", f"no price for {provider}/{model or '?'}: add one to {user_files()[0]} (see the comments in the packaged prices.toml)")
    fresh = max(usage.prompt - usage.cached - usage.cache_write, 0)
    usd = (fresh * p.input + usage.cached * (p.cache_read if p.cache_read is not None else p.input)
           + usage.cache_write * (p.cache_write if p.cache_write is not None else p.input) + usage.completion * p.output) / 1e6
    note = f"{p.source}" + (f", as of {p.as_of}" if p.as_of else "")
    if usage.missing:
        note += f"; {usage.missing} of {usage.requests} responses had no usage, so this is a lower bound"
    return Cost(round(usd, 6), "model listing" if p.source == "model listing" else "price table", note)
