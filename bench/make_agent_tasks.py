"""Builds the non-coding agent tasks (bench/tasks-agent/*) and two mixed research-then-code tasks (bench/tasks/*).

  python bench/make_agent_tasks.py            # (re)writes every task; deterministic (fixed seeds, immutable web pages)

Ground truth is never typed by hand: fixtures are generated with the answer known by construction, code questions are answered by
walking the syntax tree of the pinned source, and web questions are answered from immutable pages (RFC text, a PEP header) that the
generator fetches and checks. Each task also gets `oracle.txt`, a perfect answer, so the graders can be tested against it.
"""
from __future__ import annotations

import ast
import json
import random
import re
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
OUT = HERE / "tasks-agent"
sys.path.insert(0, str(HERE))
import graders  # noqa: E402

CLICK = HERE / ".cache" / "pallets_click"
CLICK_COMMIT = "648d7c403829013ade629d63ddbfe808f6b2b770"      # the parent commit of the deprecated-label task: a pinned tree
JSON_FMT = "Reply with only one JSON object, no prose: {fmt}"
CITE_FMT = ('Reply with only a JSON list. Each item is {"fact": "<one claim, in your words>", "url": "<the page you read it on>", '
            '"quote": "<words copied exactly from that page, at least 20 characters>"}. Every claim needs its own source and quote.')


def write(name: str, spec: dict, oracle: str, work: dict[str, str] | None = None, copy_tree: tuple[Path, str] | None = None) -> None:
    d = OUT / name
    if d.exists():
        shutil.rmtree(d)
    (d / "work").mkdir(parents=True)
    for rel, text in (work or {}).items():
        p = d / "work" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf8", newline="\n")
    if copy_tree:
        src, dest = copy_tree
        shutil.copytree(src, d / "work" / dest)
    (d / "task.yaml").write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=130), encoding="utf8")
    (d / "oracle.txt").write_text(oracle, encoding="utf8")
    print(f"  {name:28} {spec['workload']:13} work files: {sum(1 for _ in (d / 'work').rglob('*') if _.is_file())}")


# -------------------------------------------------------------------------------------------------------- code reading (click)
def click_tree(tmp: Path) -> Path:
    if not CLICK.exists():
        raise SystemExit("bench/.cache/pallets_click is missing: run any real task once (bench/real_tasks.py) to clone it")
    tmp.mkdir(parents=True, exist_ok=True)
    arch = subprocess.run(["git", "archive", CLICK_COMMIT, "src/click"], cwd=CLICK, capture_output=True)
    if arch.returncode:
        raise SystemExit(arch.stderr.decode()[-300:])
    subprocess.run(["tar", "-x", "-C", str(tmp)], input=arch.stdout, check=True)
    return tmp / "src"


def calls_named(src: str, name: str) -> list[str]:
    out = []
    for cls in [n for n in ast.parse(src).body if isinstance(n, ast.ClassDef)]:
        for fn in [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    f = node.func
                    if (isinstance(f, ast.Attribute) and f.attr == name) or (isinstance(f, ast.Name) and f.id == name):
                        out.append(f"{cls.name}.{fn.name}")
                        break
    return out


def paramtype_names(src: str) -> list[tuple[str, str]]:
    out = []
    for cls in [n for n in ast.parse(src).body if isinstance(n, ast.ClassDef)]:
        bases = [b.value if isinstance(b, ast.Subscript) else b for b in cls.bases]       # ParamType[str] is still a direct subclass
        if not any(isinstance(b, ast.Name) and b.id == "ParamType" for b in bases):
            continue
        for st in cls.body:
            if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "name" for t in st.targets) \
                    and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
                out.append((cls.name, st.value.value))
    return out


def build_code_reading() -> None:
    tmp = HERE / ".cache" / "agent_click_tree"
    if tmp.exists():
        shutil.rmtree(tmp)
    src = click_tree(tmp)
    core, types = (src / "click" / "core.py").read_text(encoding="utf8"), (src / "click" / "types.py").read_text(encoding="utf8")
    r1 = sorted(calls_named(core, "invoke"))
    r2 = paramtype_names(types)
    assert len(r1) >= 4 and len(r2) >= 5, (r1, r2)
    print("   invoke callers:", r1)
    print("   ParamType subclasses:", r2)
    write("read_invoke_callers", {
        "workload": "code_reading", "needs_web": False,
        "prompt": ("In this repository's src/click/core.py, list every method of every class that calls invoke(...) anywhere in its body "
                   "(a call on any object counts, e.g. ctx.invoke(...) or self.invoke(...)). Do not include module-level functions or calls in other files."),
        "format": "One `ClassName.method_name` per line, nothing else.",
        "grader": {"type": "lines", "lines": r1}}, "\n".join(r1) + "\n", copy_tree=(src, "src"))
    write("read_paramtype_names", {
        "workload": "code_reading", "needs_web": False,
        "prompt": ("In this repository's src/click/types.py, find every class that directly subclasses ParamType (it is named in the class's "
                   "own bases), and for each one the string value of its class attribute `name`. Skip classes that do not assign a string to `name`."),
        "format": "One `ClassName: name` per line, nothing else.",
        "grader": {"type": "lines", "lines": [f"{c}: {n}" for c, n in r2]}}, "\n".join(f"{c}: {n}" for c, n in r2) + "\n", copy_tree=(src, "src"))
    shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------------------------------------------------- exact fetch / web
def build_web() -> None:
    """Web tasks. Everything the models could know from training is a control; the real tests use RFCs published after June 2026."""
    for gone in ("fetch_rfc9110_4xx", "research_retry_after_rfc", "research_pep_match"):       # earlier drafts: memorisable
        shutil.rmtree(OUT / gone, ignore_errors=True)
    rfc6455 = graders.fetch_page("https://www.rfc-editor.org/rfc/rfc6455.txt")
    assert rfc6455 and "%x0 denotes a continuation frame" in rfc6455 and "%xA denotes a pong" in rfc6455
    ops = [[0, "continuation"], [1, "text"], [2, "binary"], [8, "close"], [9, "ping"], [10, "pong"]]
    write("control_rfc6455_opcodes", {
        "workload": "memorised_control", "needs_web": True,
        "prompt": ("RFC 6455 (the WebSocket protocol, https://www.rfc-editor.org/rfc/rfc6455.txt), section 5.2, defines the values of the frame "
                   "opcode. List the opcodes that the RFC gives a meaning to (leave out the ranges it only reserves)."),
        "format": "One per line as `0xN meaning`, using one of the words continuation, text, binary, close, ping, pong. Nothing else.",
        "grader": {"type": "regex_set", "regex": r"0x([0-9a-f]+)\W+(continuation|text|binary|close|ping|pong)", "cast": ["int16", "lower"], "expected": ops}},
        "\n".join(f"0x{v:X} {w}" for v, w in ops) + "\n")
    shutil.rmtree(OUT / "fetch_rfc6455_opcodes", ignore_errors=True)

    r9995, r10075, r10070, r10050 = (graders.fetch_page(f"https://www.rfc-editor.org/rfc/rfc{n}.txt") for n in (9995, 10075, 10070, 10050))
    assert all((r9995, r10075, r10070, r10050)), "the post-cutoff RFCs could not be fetched"
    assert all(x in r9995 for x in ("payload-hash-alg", "preimage-", "payload-", "258", "259", "260")) and "RFC 9995" in r9995
    cose = ["payload-hash-alg: 258", "preimage-content-type: 259", "payload-location: 260"]
    write("fetch_rfc9995_cose_labels", {
        "workload": "exact_fetch", "needs_web": True,
        "prompt": ("RFC 9995 (https://www.rfc-editor.org/rfc/rfc9995.txt, published July 2026) registers new COSE header parameters. "
                   "List each parameter it registers with its label number."),
        "format": "One per line as `name: label`, for example `alg: 1`. Nothing else.",
        "grader": {"type": "lines", "lines": cose}}, "\n".join(cose) + "\n")
    assert "bit 6 in the RA Flags Extension Option" in " ".join(r10075.split()) and "S - SNAC Router Flag" in r10075
    write("fetch_rfc10075_snac_bit", {
        "workload": "exact_fetch", "needs_web": True,
        "prompt": ("RFC 10075 (https://www.rfc-editor.org/rfc/rfc10075.txt, October 2026) defines the SNAC Router flag. Which bit of the RA Flags "
                   "Extension Option is it, and what one-letter name does the IANA table in that RFC give the flag?"),
        "format": JSON_FMT.format(fmt='{"bit": <number>, "letter": "<letter>"}'),
        "grader": {"type": "json", "expected": {"bit": 6, "letter": "S"}}}, json.dumps({"bit": 6, "letter": "S"}) + "\n")
    f10070 = " ".join(r10070.split())
    assert "updates RFCs 7521, 7522, 7523, and 9126" in f10070 and "be used as the sole value of the audience of the JWT client authentication assertion" in f10070
    write("research_oauth_audience", {
        "workload": "web_research", "needs_web": True,
        "prompt": ("A 2026 RFC updates RFC 7521, RFC 7522, RFC 7523 and RFC 9126 to fix a vulnerability caused by ambiguous audience values in "
                   "OAuth 2.0 client assertions. Which RFC is it, and what must the audience of a JWT client authentication assertion now be?"),
        "format": CITE_FMT,
        "grader": {"type": "facts_cites", "facts": [r"rfc ?10070", r"issuer identifier", r"sole"]}},
        json.dumps([
            {"fact": "RFC 10070 updates RFCs 7521, 7522, 7523 and 9126 on audience values", "url": "https://www.rfc-editor.org/rfc/rfc10070.txt",
             "quote": "This document updates RFCs 7521, 7522, 7523, and 9126 with respect to the treatment of audience values"},
            {"fact": "The issuer identifier of the authorization server must be the sole audience value", "url": "https://www.rfc-editor.org/rfc/rfc10070.txt",
             "quote": "be used as the sole value of the audience of the JWT client authentication assertion"}]) + "\n")
    f10050 = " ".join(r10050.split())
    assert 'IANA has created the "JSContact Profiles" registry' in f10050 and '"Specification Required"' in f10050 and "Name: This is the name of the profile." in f10050
    write("research_jscontact_registry", {
        "workload": "web_research", "needs_web": True,
        "prompt": ("Which 2026 RFC creates an IANA registry named 'JSContact Profiles'? What registration policy applies to defining a new profile "
                   "name or version, and what fields must every entry in that registry have?"),
        "format": CITE_FMT,
        "grader": {"type": "facts_cites", "facts": [r"rfc ?10050", r"specification required", r"(?=.*\bname\b)(?=.*\bversion\b)(?=.*\breference\b)"]}},
        json.dumps([
            {"fact": "RFC 10050 created the JSContact Profiles registry", "url": "https://www.rfc-editor.org/rfc/rfc10050.txt",
             "quote": 'IANA has created the "JSContact Profiles" registry within the "JSContact" registry group'},
            {"fact": "Defining a new profile name or version needs Specification Required", "url": "https://www.rfc-editor.org/rfc/rfc10050.txt",
             "quote": 'The registry policy to add an entry to this registry is "Specification Required"'},
            {"fact": "Every entry has a Name, a Version and a Reference", "url": "https://www.rfc-editor.org/rfc/rfc10050.txt",
             "quote": "An entry in this registry consists of the following, all of which MUST be set"}]) + "\n")


# ------------------------------------------------------------------------------------------------------------------ summarise
def build_log() -> None:
    rnd = random.Random(7)
    services = ["api-gateway", "auth", "payments", "inventory", "search", "notifications", "db-proxy", "cache", "scheduler", "billing", "mailer", "reports"]
    day = datetime(2025, 10, 14, 13, 0, 0)
    rows = []
    for _ in range(4100):
        t = day + timedelta(seconds=rnd.uniform(0, 7200))
        s = rnd.choice(services)
        r = rnd.random()
        if r < 0.78:
            msg = ("INFO", rnd.choice([f"request completed in {rnd.randint(3, 480)}ms status=200", f"job {rnd.randint(1000, 9999)} finished fatal=false",
                                       f"cache hit ratio {rnd.randint(70, 99)}%", f"heartbeat ok peers={rnd.randint(3, 12)}", "config reloaded"]))
        elif r < 0.93:
            msg = ("WARN", rnd.choice([f"slow query {rnd.randint(300, 1200)}ms code=W{rnd.randint(1000, 1099)}", f"retrying in {rnd.randint(1, 5)}s code=W{rnd.randint(1000, 1099)}",
                                       "queue depth above soft limit"]))
        else:
            msg = ("ERROR", f"upstream timeout code=E{rnd.choice([4470, 4472, 4473, 1204, 2210, 3319])} recovered after retry")
        rows.append((t, s, *msg))
    planted = [("14:07:31", "db-proxy", "ERROR", "connection pool exhausted code=E4471"),
               ("14:07:48", "payments", "FATAL", "unable to commit transaction, giving up: code=E4471"),
               ("14:08:02", "inventory", "FATAL", "stock write failed, giving up: code=E4471"),
               ("14:08:15", "auth", "FATAL", "session store unavailable, giving up: code=E4471"),
               ("14:09:12", "payments", "FATAL", "unable to commit transaction, giving up: code=E4471"),
               ("14:09:40", "auth", "FATAL", "session store unavailable, giving up: code=E4471")]
    for hhmmss, s, lvl, m in planted:
        rows.append((datetime.strptime(f"2025-10-14 {hhmmss}", "%Y-%m-%d %H:%M:%S") + timedelta(milliseconds=rnd.randint(0, 999)), s, lvl, m))
    rows.sort()
    text = "".join(f"{t:%Y-%m-%d %H:%M:%S}.{t.microsecond // 1000:03d} {lvl:5} {s} {m}\n" for t, s, lvl, m in rows)
    first = {"payments": "14:07:48", "inventory": "14:08:02", "auth": "14:08:15"}
    exp = {"fatal": first, "root_cause": "E4471"}
    write("summarise_incident_log", {
        "workload": "summarise", "needs_web": False,
        "prompt": ("server.log is a two-hour log from one deployment. Some services logged an entry at level FATAL. Find which services did, "
                   "the time (HH:MM:SS) of each service's first FATAL entry, and the root cause: the error code of the earliest ERROR line "
                   "in the whole log whose code is the one the FATAL entries give up on."),
        "format": JSON_FMT.format(fmt='{"fatal": {"<service>": "HH:MM:SS", ...}, "root_cause": "E...."}'),
        "grader": {"type": "json", "expected": exp}}, json.dumps(exp) + "\n", work={"server.log": text})


def build_changelog() -> None:
    rnd = random.Random(11)
    versions, v = [], [1, 0, 0]
    for _ in range(300):
        versions.append(".".join(map(str, v)))
        step = rnd.random()
        if step < 0.08:
            v = [v[0] + 1, 0, 0]
        elif step < 0.4:
            v = [v[0], v[1] + 1, 0]
        else:
            v = [v[0], v[1], v[2] + 1]
    breaking = sorted(rnd.sample(range(5, 295), 7))
    bv = [versions[i] for i in breaking]
    lines = ["# Changelog", ""]
    for i, ver in enumerate(versions):
        lines.append(f"## {ver}")
        for _ in range(rnd.randint(2, 5)):
            tag = rnd.choice(["feature", "fix", "fix", "perf", "docs", "deprecated"])
            body = rnd.choice(["tighten input validation", "faster startup", "handle empty config", "fix race in scheduler", "update dependency pins",
                               "clearer error text", "add retry to uploads", "trim log noise", "support new locale"]) + f" ({rnd.randint(100, 9999)})"
            if tag == "deprecated":
                body += " -- this will become a BREAKING change in a later major version"
            if tag == "fix" and rnd.random() < 0.15:
                body += "; no breaking changes for existing callers"
            lines.append(f"- [{tag}] {body}")
        if i in breaking:
            lines.append(f"- [BREAKING] {rnd.choice(['rename config key', 'drop python 3.8', 'change default timeout', 'remove legacy cli flag'])} ({rnd.randint(100, 9999)})")
        lines.append("")
    write("summarise_changelog_breaking", {
        "workload": "summarise", "needs_web": False,
        "prompt": ("CHANGELOG.md has an entry per release. Some entries carry an entry tagged exactly [BREAKING]. Which versions have one? "
                   "Mentions of the word breaking in other entries do not count."),
        "format": "One version number per line, for example `2.4.1`. Nothing else.",
        "grader": {"type": "lines", "lines": bv}}, "\n".join(bv) + "\n", work={"CHANGELOG.md": "\n".join(lines) + "\n"})


# --------------------------------------------------------------------------------------------------------------------- wrangle
def build_orders() -> None:
    rnd = random.Random(21)
    regions = ["north", "south", "east", "west", "central", "overseas"]
    rows, totals = ["order_id,region,status,amount,date"], {r: 0.0 for r in regions}
    for i in range(5000):
        d = datetime(2025, 1, 1) + timedelta(days=rnd.randint(0, 364))
        r, st, amt = rnd.choice(regions), rnd.choice(["shipped", "shipped", "pending", "cancelled", "returned"]), round(rnd.lognormvariate(4.6, 0.8), 2)
        rows.append(f"{i + 1},{r},{st},{amt:.2f},{d:%Y-%m-%d}")
        if st == "shipped" and datetime(2025, 7, 1) <= d <= datetime(2025, 9, 30):
            totals[r] += amt
    exp = {r: round(t, 2) for r, t in totals.items()}
    write("wrangle_orders_revenue", {
        "workload": "data_wrangle", "needs_web": False,
        "prompt": ("orders.csv has one row per order. Compute the total amount per region for orders whose status is exactly 'shipped' and whose "
                   "date is between 2025-07-01 and 2025-09-30 inclusive. Round each total to 2 decimals."),
        "format": JSON_FMT.format(fmt='{"<region>": <total>, ...} with every region of the file'),
        "grader": {"type": "json", "expected": exp, "tol": 0.01}}, json.dumps(exp) + "\n", work={"orders.csv": "\n".join(rows) + "\n"})


def build_events() -> None:
    rnd = random.Random(31)
    ev, deltas, ok = [], [], 0
    for u in range(1, 701):
        uid = f"u{u:04d}"
        s = datetime(2025, 3, 1) + timedelta(minutes=rnd.randint(0, 40 * 24 * 60))
        ev.append((s, uid, "signup"))
        purchases = [s + timedelta(minutes=rnd.choice([rnd.randint(1, 1600), rnd.randint(1700, 9000)])) for _ in range(rnd.choice([0, 0, 1, 1, 2, 3]))]
        for p in purchases:
            ev.append((p, uid, "purchase"))
        within = sorted(p for p in purchases if timedelta(0) <= p - s <= timedelta(hours=24))
        if within:
            ok += 1
            deltas.append((within[0] - s).total_seconds() / 3600)
        for _ in range(rnd.randint(0, 4)):
            ev.append((s + timedelta(minutes=rnd.randint(0, 5000)), uid, "pageview"))
    ev.sort()
    exp = {"users": ok, "median_hours": round(statistics.median(deltas), 2)}
    text = "".join(json.dumps({"user": u, "event": e, "ts": f"{t:%Y-%m-%dT%H:%M:%SZ}"}) + "\n" for t, u, e in ev)
    write("wrangle_events_conversion", {
        "workload": "data_wrangle", "needs_web": False,
        "prompt": ("events.jsonl has one event per line (user, event, ts in UTC). For each user with a 'signup' event, look for a 'purchase' by the "
                   "same user between 0 and 24 hours (inclusive) after the signup. Count the users that have at least one, and give the median, "
                   "over those users, of the hours between the signup and their earliest such purchase, rounded to 2 decimals."),
        "format": JSON_FMT.format(fmt='{"users": <count>, "median_hours": <number>}'),
        "grader": {"type": "json", "expected": exp, "tol": 0.01}}, json.dumps(exp) + "\n", work={"events.jsonl": text})


# ----------------------------------------------------------------------------------------------- mixed: read the RFC, then code
def build_mixed() -> None:
    rfc = graders.fetch_page("https://www.rfc-editor.org/rfc/rfc9110.txt")
    assert "MUST NOT attempt to recombine" in rfc and "obsolete" in rfc.lower()
    tasks = HERE / "tasks"
    specs = {
        "retry_after_rfc": dict(
            brief=("Implement parse_retry_after(value, now) in retry_after.py, following RFC 9110 section 10.2.3 (the Retry-After field) and the "
                   "HTTP date rules it refers to, from https://www.rfc-editor.org/rfc/rfc9110.txt. `now` is a naive datetime in UTC. Return the "
                   "number of seconds to wait as a float, never negative (a date already past gives 0.0). Raise ValueError for a value that is "
                   "neither of the field's two forms. Read the RFC for exactly which date formats a recipient must accept."),
            stub='from datetime import datetime\n\n\ndef parse_retry_after(value: str, now: datetime) -> float:\n    raise NotImplementedError\n',
            visible=('from datetime import datetime\n\nfrom retry_after import parse_retry_after\n\nNOW = datetime(1999, 12, 31, 23, 59, 0)\n\n\n'
                     'def test_delay_seconds():\n    assert parse_retry_after("120", NOW) == 120.0\n\n\n'
                     'def test_http_date():\n    assert parse_retry_after("Fri, 31 Dec 1999 23:59:59 GMT", NOW) == 59.0\n'),
            hidden=('from datetime import datetime\n\nimport pytest\n\nfrom retry_after import parse_retry_after\n\nNOW = datetime(1999, 12, 31, 23, 59, 0)\n\n\n'
                    'def test_zero_and_spaces():\n    assert parse_retry_after("0", NOW) == 0.0\n    assert parse_retry_after(" 30 ", NOW) == 30.0\n\n\n'
                    '@pytest.mark.parametrize("bad", ["-5", "1.5", "abc", "", "Fri, 31 Dec 1999"])\ndef test_invalid(bad):\n    with pytest.raises(ValueError):\n        parse_retry_after(bad, NOW)\n\n\n'
                    'def test_obsolete_rfc850():\n    assert parse_retry_after("Friday, 31-Dec-99 23:59:59 GMT", NOW) == 59.0\n\n\n'
                    'def test_obsolete_asctime():\n    assert parse_retry_after("Fri Dec 31 23:59:59 1999", NOW) == 59.0\n\n\n'
                    'def test_past_date_is_zero():\n    assert parse_retry_after("Thu, 30 Dec 1999 00:00:00 GMT", NOW) == 0.0\n\n\n'
                    'def test_rfc850_two_digit_year_in_the_past_century():\n    later = datetime(2024, 1, 1)\n    assert parse_retry_after("Sunday, 06-Nov-94 08:49:37 GMT", later) == 0.0\n'),
            file="retry_after.py"),
        "content_range_rfc": dict(
            brief=("Implement parse_content_range(value) in content_range.py following RFC 9110 section 14.4 (the Content-Range field), from "
                   "https://www.rfc-editor.org/rfc/rfc9110.txt. Return a dict with the keys unit, first, last, length (ints, or None for what the "
                   "value does not say). Raise ValueError for a value that is malformed or that the RFC defines as invalid. Read the RFC for "
                   "the forms the field can take and for what makes a value invalid."),
            stub='def parse_content_range(value: str) -> dict:\n    raise NotImplementedError\n',
            visible=('from content_range import parse_content_range\n\n\ndef test_simple_range():\n    assert parse_content_range("bytes 0-499/1234") == '
                     '{"unit": "bytes", "first": 0, "last": 499, "length": 1234}\n'),
            hidden=('import pytest\n\nfrom content_range import parse_content_range\n\n\n'
                    'def test_unknown_length():\n    assert parse_content_range("bytes 0-499/*") == {"unit": "bytes", "first": 0, "last": 499, "length": None}\n\n\n'
                    'def test_unsatisfied_range():\n    assert parse_content_range("bytes */1234") == {"unit": "bytes", "first": None, "last": None, "length": 1234}\n\n\n'
                    'def test_last_byte_is_allowed():\n    assert parse_content_range("bytes 0-1233/1234")["last"] == 1233\n\n\n'
                    'def test_other_range_units_are_allowed():\n    assert parse_content_range("items 0-9/100") == {"unit": "items", "first": 0, "last": 9, "length": 100}\n\n\n'
                    '@pytest.mark.parametrize("bad", ["bytes 500-499/1234", "bytes 0-1234/1234", "bytes 0-499/300", "bytes */*", "bytes 0-499", "", "0-499/1234"])\n'
                    'def test_invalid(bad):\n    with pytest.raises(ValueError):\n        parse_content_range(bad)\n'),
            file="content_range.py"),
    }
    for name, s in specs.items():
        d = tasks / name
        if d.exists():
            shutil.rmtree(d)
        (d / "repo").mkdir(parents=True)
        (d / "hidden").mkdir()
        (d / "repo" / s["file"]).write_text(s["stub"], encoding="utf8", newline="\n")
        (d / "repo" / f"test_{s['file']}").write_text(s["visible"], encoding="utf8", newline="\n")
        (d / "hidden" / "test_hidden.py").write_text(s["hidden"], encoding="utf8", newline="\n")
        (d / "task.yaml").write_text(yaml.safe_dump({"brief": s["brief"], "allowed_paths": [s["file"]],
                                                     "acceptance": [{"cmd": f"python -m pytest -q test_{s['file']}", "timeout_s": 120}]}, sort_keys=False, width=130), encoding="utf8")
        print(f"  {name:28} mixed         (tasks/)")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    print("building tasks-agent:")
    build_code_reading()
    build_web()
    build_log()
    build_changelog()
    build_orders()
    build_events()
    build_mixed()
