"""Deterministic graders for the non-coding agent tasks (bench/tasks-agent/). No model judges anything here.

A task's `grader:` block picks one:

  lines        expected `lines:`; the answer's lines are normalised (case, bullets, backticks, punctuation, spaces) and compared as a set.
               score = F1 of precision and recall; pass = F1 of 1.
  regex_set    each answer line is read with `regex:` into a tuple (groups cast by `cast:` -- int16, lower, int); compared with `expected:`.
  json         the answer holds one JSON object; every expected leaf (dotted path) must match (numbers within `tol`). score = share correct.
  facts_cites  research with sources. The answer is a JSON list of {"fact", "url", "quote"}. `facts:` are regexes that must each match
               some fact; every cited quote must occur (whitespace and case folded) in the text of the page at its url. The pages are
               fetched with `fetch_page`, which caches them under bench/.cache/pages. score = half fact recall + half share of valid
               citations; pass = every fact present and every citation valid and at least one citation.

`grade(spec, answer_text)` returns {"score": 0..1, "passed": bool, "detail": {...}}.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
from pathlib import Path

CACHE = Path(__file__).parent / ".cache" / "pages"


# ------------------------------------------------------------------------------------------------------------- text helpers
def fold(s: str) -> str:
    """Case, whitespace and typographic quotes/dashes folded, so a quote copied from a page still matches."""
    s = html.unescape(s)
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    s = s.replace(" ", " ").replace("﻿", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def norm_line(line: str) -> str:
    line = line.strip().strip("`*_ ").lstrip("-*• ").strip()
    line = re.sub(r"^\d+[.)]\s+", "", line)
    line = line.replace("`", "").replace("**", "")
    line = re.sub(r"\s*:\s*", ": ", line)
    line = re.sub(r"[\"'.,;]+$", "", line)
    return re.sub(r"\s+", " ", line).strip().lower()


def answer_lines(text: str) -> list[str]:
    text = re.sub(r"```[a-z]*", "", text)
    return [norm_line(l) for l in text.splitlines() if norm_line(l)]


def first_json(text: str):
    """The first JSON object or array in the text (fences and chatter around it tolerated), or None."""
    text = re.sub(r"```[a-z]*", "", text)
    dec = json.JSONDecoder()
    for m in re.finditer(r"[\[{]", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
            return obj
        except ValueError:
            continue
    return None


def f1(expected: set, got: set) -> tuple[float, float, float]:
    if not expected and not got:
        return 1.0, 1.0, 1.0
    tp = len(expected & got)
    p = tp / len(got) if got else 0.0
    r = tp / len(expected) if expected else 0.0
    return (2 * p * r / (p + r) if p + r else 0.0), p, r


# ------------------------------------------------------------------------------------------------------------------- pages
def fetch_page(url: str) -> str | None:
    """Text of a page (tags stripped if it is HTML), cached on disk. None when it cannot be fetched."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".txt")
    if f.exists():
        return f.read_text(encoding="utf8")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gruntly-bench/1.0"})
        raw = urllib.request.urlopen(req, timeout=60).read().decode("utf8", "replace")
    except Exception:  # noqa: BLE001 - an unreachable page means the citation cannot be checked, which counts against it
        return None
    if "<html" in raw[:2000].lower() or "<body" in raw[:5000].lower():
        raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
        raw = re.sub(r"<[^>]+>", " ", raw)
    f.write_text(raw, encoding="utf8")
    return raw


# ----------------------------------------------------------------------------------------------------------------- graders
def grade_lines(g: dict, answer: str) -> dict:
    exp = {norm_line(x) for x in g["lines"]}
    got = set(answer_lines(answer))
    score, p, r = f1(exp, got)
    return {"score": score, "passed": exp == got, "detail": {"precision": round(p, 3), "recall": round(r, 3),
            "missing": sorted(exp - got)[:15], "extra": sorted(got - exp)[:15]}}


def grade_regex_set(g: dict, answer: str) -> dict:
    rx = re.compile(g["regex"], re.I)
    casts = {"int16": lambda s: int(s, 16), "int": int, "lower": str.lower, "str": str}
    kinds = g.get("cast", [])

    def tup(groups):
        return tuple((casts[kinds[i]] if i < len(kinds) else str)(x) for i, x in enumerate(groups))
    got = set()
    for line in answer.splitlines():
        m = rx.search(line)
        if m:
            try:
                got.add(tup(m.groups()))
            except ValueError:
                pass
    exp = {tuple(e) for e in g["expected"]}
    score, p, r = f1(exp, got)
    return {"score": score, "passed": exp == got, "detail": {"precision": round(p, 3), "recall": round(r, 3),
            "missing": sorted(map(str, exp - got))[:15], "extra": sorted(map(str, got - exp))[:15]}}


def _leaves(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaves(v, f"{prefix}{k}.")
    elif isinstance(obj, list):
        yield prefix.rstrip("."), sorted(map(str, obj))
    else:
        yield prefix.rstrip("."), obj


def grade_json(g: dict, answer: str) -> dict:
    got = first_json(answer)
    if not isinstance(got, dict):
        return {"score": 0.0, "passed": False, "detail": {"error": "no JSON object in the answer"}}
    gl, tol = dict(_leaves(got)), float(g.get("tol", 0.01))
    ok, bad = 0, []
    exp = dict(_leaves(g["expected"]))
    for path, want in exp.items():
        have = gl.get(path)
        if isinstance(want, (int, float)) and isinstance(have, (int, float)) and abs(want - have) <= tol:
            ok += 1
        elif isinstance(want, list) and have == want:
            ok += 1
        elif isinstance(want, str) and isinstance(have, str) and fold(want) == fold(have):
            ok += 1
        elif want == have:
            ok += 1
        else:
            bad.append(f"{path}: expected {want!r}, got {have!r}")
    extra = [p for p in gl if p not in exp][:10]
    return {"score": ok / len(exp), "passed": ok == len(exp) and not extra, "detail": {"wrong": bad[:12], "extra_keys": extra}}


def grade_facts_cites(g: dict, answer: str) -> dict:
    items = first_json(answer)
    if isinstance(items, dict):
        items = items.get("facts") or items.get("answer") or [items]
    if not isinstance(items, list):
        return {"score": 0.0, "passed": False, "detail": {"error": "no JSON list of facts in the answer"}}
    items = [i for i in items if isinstance(i, dict)]
    blob = " ".join(fold(str(i.get("fact", "")) + " " + str(i.get("quote", ""))) for i in items)
    facts = [(f, bool(re.search(f, blob, re.I))) for f in g["facts"]]
    recall = sum(1 for _, ok in facts if ok) / len(facts)
    cites, valid = [], 0
    for i in items:
        url, quote = str(i.get("url", "")), fold(str(i.get("quote", "")))
        page = fetch_page(url) if url.startswith("http") and len(quote) >= int(g.get("min_quote", 15)) else None
        found = bool(page) and quote in fold(page)
        valid += found
        cites.append({"url": url[:90], "quote": quote[:70], "found": found})
    share = valid / len(items) if items else 0.0
    return {"score": 0.5 * recall + 0.5 * share, "passed": recall == 1 and items != [] and valid == len(items),
            "detail": {"facts_found": [f for f, ok in facts if ok], "facts_missing": [f for f, ok in facts if not ok],
                       "citations": len(items), "citations_valid": valid, "checked": cites[:8]}}


GRADERS = {"lines": grade_lines, "regex_set": grade_regex_set, "json": grade_json, "facts_cites": grade_facts_cites}


def grade(spec: dict, answer: str) -> dict:
    g = spec["grader"]
    return GRADERS[g["type"]](g, answer or "")
