#!/usr/bin/env python3
"""Builds the delegation export (runs.csv, timeline_sample.csv, README.md) from existing experiment data.

Read-only: it reads the benchmark result files, the per-run stream-json transcripts, the gruntly run records, the persisted
Claude Code session logs and the LM Studio server logs, and writes only into --out. It never runs a model, never writes into the
repo, and exports numbers and short labels only (no prompts, code, transcripts, paths, keys or environment).

    python bench/delegation_export.py [--repo PATH] [--claude-projects PATH] [--lmstudio-logs PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------------------------------------------------
# Price table, $ per million tokens. Sonnet and Opus input/output/cache-read/1h-write and Haiku all four rates were fitted
# from Claude Code's own per-model costUSD (modelUsage) in these runs and reproduce it to the cent-fraction; the 5-minute
# write rate is verified for Haiku only (sub-agents write 5-minute caches) and is the 1.25x-input pattern for the others.
PRICES = {
    "claude-sonnet-5-5": {"inp": 2.0, "out": 10.0, "read": 0.10, "w5": 2.5, "w1": 4.0},
    "claude-opus-5-5": {"inp": 4.0, "out": 20.0, "read": 0.20, "w5": 5.0, "w1": 8.0},
    "claude-haiku-5-5": {"inp": 0.10, "out": 0.50, "read": 0.01, "w5": 0.125, "w1": 0.20},
}
WEB_SEARCH_USD = 0.01
ALIASES = {"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5", "haiku": "claude-haiku-5-5"}

# task type by hand from each task's first sentence (bench/tasks*/<task>/task.yaml)
TASK_TYPE = {
    "bugs_batch": "bug fix", "merge_intervals": "bug fix", "paginate": "bug fix", "word_count": "bug fix",
    "rename_domain": "bulk edit", "settings_refactor": "refactor",
    "cli_json": "other", "inventory_reorder": "other", "flatten": "other", "lru_cache": "other", "parse_duration": "other",
    "retry": "other", "roman": "other", "rolling_mean": "other", "slugify": "other", "retry_after_rfc": "other",
    "content_range_rfc": "other",
    "control_rfc6455_opcodes": "read-heavy", "fetch_rfc10075_snac_bit": "read-heavy", "fetch_rfc9995_cose_labels": "read-heavy",
    "read_invoke_callers": "read-heavy", "read_paramtype_names": "read-heavy", "research_jscontact_registry": "read-heavy",
    "research_oauth_audience": "read-heavy", "summarise_changelog_breaking": "read-heavy", "summarise_incident_log": "read-heavy",
    "wrangle_events_conversion": "other", "wrangle_orders_revenue": "other",
}
DELEGATED_ARMS = {"forced", "policy", "gd", "gdA", "gdAB", "lean", "planner", "subagent", "gruntly", "auto"}
PARENT_ALONE_ARMS = {"alone", "lean_alone"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
BASH_TOOLS = {"Bash", "PowerShell"}
BASH_WRITE = re.compile(r"(\bsed\s+-i\b|\btee\b|\bSet-Content\b|\bAdd-Content\b|\bOut-File\b|\bgit\s+apply\b|\bpatch\s+-|\bcat\s*>)")
INSPECT_TOOLS = {"Read", "Grep", "Glob", "NotebookRead"}
GRUNTLY_VERB = re.compile(r"gruntly(?:\.exe)?\"?\s+(agent-run|wait|continue|diff|apply|discard|do|run|mode|stats|doctor|rules|status)\b")
RUNNING_VERBS = {"agent-run", "continue", "wait", "do", "run"}
STAT_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")

COLUMNS = [
    "run_id", "task_id", "task_type", "arm", "arm_detail", "delegation_occurred", "experiment", "rep", "run_date",
    "parent_harness", "parent_model", "child_harness", "child_model", "child_runtime", "quantization", "child_context_window",
    "parent_uncached_input", "parent_cache_read", "parent_cache_write", "parent_output", "parent_turns",
    "child_input_tokens", "child_output_tokens", "child_tokens_total", "child_turns",
    "brief_tokens", "brief_chars", "verification_method", "verification_tokens",
    "child_claimed_success", "tests_passed_after_child", "final_pass", "rebrief_count", "gruntly_attempts", "gruntly_status",
    "takeover", "parent_tokens_after_takeover", "parent_cost_after_takeover_usd",
    "wall_time_total_s", "child_wall_s", "parent_idle_s_while_child_ran", "max_gap_between_parent_api_calls_s",
    "failure_reason",
    "cost_usd_computed", "cost_usd_reported", "cost_diff_usd", "child_cost_usd_computed", "child_cost_usd_reported",
    "other_models_cost_usd_reported",
    "data_source", "parent_tokens_source", "child_tokens_source", "output_tokens_reconcile", "cache_ttl_main_thread",
]
TIMELINE_COLUMNS = ["run_id", "outcome_group", "call_index", "timestamp_utc", "seconds_since_run_start", "gap_since_prev_call_s",
                    "uncached_input", "cache_read", "cache_write", "output", "label"]


def ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else 0


def price_call(model, inp, out, read, w5, w1):
    p = PRICES.get(model)
    if not p:
        return None
    return (inp * p["inp"] + out * p["out"] + read * p["read"] + w5 * p["w5"] + w1 * p["w1"]) / 1e6


# ---------------------------------------------------------------------------------------------------------------------
# session parsing (stream-json transcripts and persisted Claude Code session logs share the event shapes used here)

def load_session(path: Path) -> dict:
    calls: dict = {}
    order: list = []
    tool_ts: dict = {}
    result = init = cost_state = None
    first = last = None
    for line in path.open(encoding="utf8", errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        t = e.get("type")
        et = ts(e.get("timestamp"))
        if et:
            first = et if first is None or et < first else first
            last = et if last is None or et > last else last
        if t == "system" and e.get("subtype") == "init" and init is None:
            init = e
        elif t == "result":
            result = e
        elif t == "cost-state":
            cost_state = e
        elif t == "assistant":
            m = e.get("message") or {}
            mid = m.get("id") or e.get("uuid")
            side = bool(e.get("isSidechain")) or e.get("parent_tool_use_id") is not None
            c = calls.get(mid)
            if c is None:
                c = calls[mid] = {"id": mid, "model": m.get("model"), "side": side, "first": et, "last": et, "u": dict.fromkeys(STAT_FIELDS, 0),
                                  "cw5": 0, "cw1": 0, "tools": [], "tool_ids": set()}
                order.append(mid)
            if et:
                c["first"] = et if c["first"] is None or et < c["first"] else c["first"]
                c["last"] = et if c["last"] is None or et > c["last"] else c["last"]
            u = m.get("usage") or {}
            for k in STAT_FIELDS:
                c["u"][k] = max(c["u"][k], num(u.get(k)))
            cc = u.get("cache_creation") or {}
            c["cw5"] = max(c["cw5"], num(cc.get("ephemeral_5m_input_tokens")))
            c["cw1"] = max(c["cw1"], num(cc.get("ephemeral_1h_input_tokens")))
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") not in c["tool_ids"]:
                    c["tool_ids"].add(b.get("id"))
                    inp = b.get("input") or {}
                    cmd = inp.get("command") if isinstance(inp, dict) else None
                    c["tools"].append({"id": b.get("id"), "name": b.get("name") or "", "cmd": cmd if isinstance(cmd, str) else "",
                                       "size": len(json.dumps(inp)), "ts": et})
        elif t == "user":
            content = (e.get("message") or {}).get("content")
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tool_ts[b.get("tool_use_id")] = et
    ordered = [calls[i] for i in order]
    return {"calls": ordered, "tool_ts": tool_ts, "result": result, "init": init, "cost_state": cost_state, "first": first, "last": last}


def call_tokens(c):
    u = c["u"]
    cw = u["cache_creation_input_tokens"]
    w5 = min(c["cw5"], cw)
    return {"inp": u["input_tokens"], "out": u["output_tokens"], "cr": u["cache_read_input_tokens"], "cw": cw, "w5": w5, "w1": cw - w5}


def gruntly_info(tool):
    """(verb, is_continue) for a tool call that talks to gruntly, else None."""
    name, cmd = tool["name"], tool["cmd"]
    if name in BASH_TOOLS and "gruntly" in cmd:
        m = GRUNTLY_VERB.search(cmd)
        verb = m.group(1) if m else "other"
        if "--continue" in cmd:
            verb = "continue"
        return verb
    if name.startswith("mcp__") and "gruntly" in name:
        return "continue" if name.endswith("manage") else "agent-run"
    return None


def analyse_session(S: dict) -> dict:
    main = [c for c in S["calls"] if not c["side"]]
    side = [c for c in S["calls"] if c["side"]]
    models = Counter(c["model"] for c in main if c["model"])
    parent_model = models.most_common(1)[0][0] if models else (S["init"] or {}).get("model")
    tool_ts = S["tool_ts"]
    g_calls = []         # (call_index, tool, verb)
    for i, c in enumerate(main):
        for t in c["tools"]:
            v = gruntly_info(t)
            if v:
                g_calls.append((i, t, v))
    starts = [x for x in g_calls if x[2] in ("agent-run", "do", "run")]
    intervals = []
    for i, t, v in g_calls:
        if v in RUNNING_VERBS and t["ts"] and tool_ts.get(t["id"]):
            intervals.append((t["ts"], tool_ts[t["id"]]))
    intervals.sort()
    idle = sum((b - a).total_seconds() for a, b in intervals)
    # delegation / takeover positions
    issue_idx = starts[0][0] if starts else None
    takeover_idx = None
    if issue_idx is not None:
        for i in range(issue_idx + 1, len(main)):
            if any(t["name"] in EDIT_TOOLS or (t["name"] in BASH_TOOLS and BASH_WRITE.search(t["cmd"]) and "gruntly" not in t["cmd"]) for t in main[i]["tools"]):
                takeover_idx = i
                break
    applied_before = any(v == "apply" and (takeover_idx is None or i < takeover_idx) for i, _, v in g_calls)
    last_end = max((b for _, b in intervals), default=None)
    first_start = intervals[0][0] if intervals else None
    labels = []
    for i, c in enumerate(main):
        t0 = c["first"]
        lab = "before_delegation"
        if issue_idx is not None and i > issue_idx:
            if t0 and any(a <= t0 < b for a, b in intervals):
                lab = "during"
            else:
                lab = "after_child_returned"
            if takeover_idx is not None and i >= takeover_idx:
                lab = "takeover"
        labels.append(lab)
    # verification: calls after the child returned, before a takeover, that look at the child's work or run tests
    verif_calls = []
    for i, c in enumerate(main):
        if issue_idx is None or i <= issue_idx or (takeover_idx is not None and i >= takeover_idx):
            continue
        if labels[i] == "during":
            continue
        for t in c["tools"]:
            if t["name"] in INSPECT_TOOLS:
                verif_calls.append((i, "inspect"))
                break
            if t["name"] in BASH_TOOLS and re.search(r"gruntly(?:\.exe)?\"?\s+diff|git\s+diff", t["cmd"]):
                verif_calls.append((i, "inspect"))
                break
            if t["name"] in BASH_TOOLS and re.search(r"pytest|unittest", t["cmd"]):
                verif_calls.append((i, "tests"))
                break
    vtok = 0
    for i, _ in verif_calls:
        vtok += call_tokens(main[i])["out"]
        if i + 1 < len(main):
            nt = call_tokens(main[i + 1])
            vtok += nt["inp"] + nt["cw"]
    gaps = []
    for a, b in zip(main, main[1:]):
        if a["last"] and b["first"]:
            gaps.append((b["first"] - a["last"]).total_seconds())
    return {"main": main, "side": side, "parent_model": parent_model, "g_calls": g_calls, "starts": starts, "intervals": intervals,
            "idle": idle if intervals else None, "issue_idx": issue_idx, "takeover_idx": takeover_idx, "applied_before": applied_before,
            "labels": labels, "verif": verif_calls, "vtok": vtok, "max_gap": max(gaps) if gaps else None, "gaps": gaps,
            "brief_chars": len(starts[0][1]["cmd"]) if starts and starts[0][1]["cmd"] else (starts[0][1]["size"] if starts else None),
            "rebrief": (max(len(starts) - 1, 0) + sum(1 for _, _, v in g_calls if v == "continue")) if g_calls else None,
            "first_start": first_start, "last_end": last_end}


# ---------------------------------------------------------------------------------------------------------------------

def md_header(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    head = " ".join(path.read_text(encoding="utf8", errors="replace").splitlines()[:6])
    m = re.search(r"Local child: `([^`]+)` / `([^`]+)`(?: at (\d+)k context)?", head)
    if m:
        out["child_harness"], out["child_model"] = m.group(1), m.group(2)
        out["ctx"] = int(m.group(3)) * 1024 if m.group(3) else None
    m = re.search(r"Parent: Claude Code \(([^)]+)\)", head)
    if m:
        out["parent"] = m.group(1)
    m = re.search(r"Run(?: on)? (\d{4}-\d\d-\d\d)", head)
    if m:
        out["date"] = m.group(1)
    return out


def child_runtime(harness, model, provider, endpoint):
    if harness == "claude":
        return "anthropic api (claude code cli)"
    if provider and provider != "local":
        return f"{provider}-hosted api"
    if model and re.match(r"(nvidia|poolside|deepseek-ai|meta|mistralai|google)/", model) and harness == "hermes":
        return "nvidia-hosted api (inferred from model id)"
    if model and re.match(r"nvidia/", model):
        return "nvidia-hosted api (inferred from model id)"
    if model and model.startswith(("gemini", "gemma")):
        return "gemini api (inferred from model id)"
    if endpoint and "127.0.0.1:1234" in endpoint or (model and model.startswith("qwen/")):
        return "lm studio (llama.cpp), local"
    return None


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf8", errors="replace"))
    except (OSError, ValueError):
        return None


def parse_child_log(p: Path):
    """Sum a Claude child's result lines: total input (uncached + cache read + cache write), cache read, output, cost, turns, markers."""
    out = {"inp": 0, "cr": 0, "cw": 0, "w5": 0, "out": 0, "cost": 0.0, "turns": 0, "exits": [], "breaches": [], "results": 0, "model": None,
           "mu": defaultdict(lambda: [0, 0, 0, 0, 0, 0.0, 0, 0])}
    try:
        text = p.read_text(encoding="utf8", errors="replace")
    except OSError:
        return out
    for m in re.finditer(r"=== attempt (\d+) exit=(\S+) breach=(\S+) ===", text):
        out["exits"].append(m.group(2))
        out["breaches"].append(m.group(3))
    for line in text.splitlines():
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "result":
            continue
        u = e.get("usage") or {}
        out["results"] += 1
        out["inp"] += num(u.get("input_tokens")) + num(u.get("cache_read_input_tokens")) + num(u.get("cache_creation_input_tokens"))
        out["cr"] += num(u.get("cache_read_input_tokens"))
        out["cw"] += num(u.get("cache_creation_input_tokens"))
        out["w5"] += num((u.get("cache_creation") or {}).get("ephemeral_5m_input_tokens"))
        out["out"] += num(u.get("output_tokens"))
        out["cost"] += num(e.get("total_cost_usd"))
        out["turns"] += num(e.get("num_turns"))
        for mname, v in (e.get("modelUsage") or {}).items():
            a = out["mu"][mname]
            for j, k in enumerate(("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "webSearchRequests")):
                a[j] += num(v.get(k))
            a[5] += num(v.get("costUSD"))
            a[6] += num(v.get("cacheCreationEphemeral5mInputTokens"))     # the TTL split of the cache writes, per model and for the whole session
            a[7] += num(v.get("cacheCreationEphemeral1hInputTokens"))
            out["model"] = mname
    return out


def main_cli():
    ap = argparse.ArgumentParser()
    home = Path.home()
    repo = Path(__file__).resolve().parent.parent
    ap.add_argument("--repo", default=str(repo))
    ap.add_argument("--claude-projects", default=str(home / ".claude" / "projects"))
    ap.add_argument("--lmstudio-logs", default=str(home / ".lmstudio" / "server-logs"))
    ap.add_argument("--out", default=str(repo / "docs" / "benchmarks" / "delegation-export"))
    a = ap.parse_args()
    build(Path(a.repo), Path(a.claude_projects), Path(a.lmstudio_logs), Path(a.out))


def build(repo: Path, proj: Path, lmlogs: Path, out: Path):
    docs = repo / "docs" / "benchmarks"
    bench = repo / "bench"
    notes: dict = defaultdict(list)          # for the README gaps section

    # ---- 1. result rows, deduplicated across files -------------------------------------------------------------------
    rows_raw = []
    seen = {}
    excluded = Counter()
    for f in sorted(docs.glob("*.json")):
        if f.name.endswith(".meta.json"):
            continue
        data = read_json(f)
        if not isinstance(data, list):
            excluded[f.stem + " (not a list of runs)"] += 1
            continue
        if f.stem.startswith("child-bench") or f.stem == "benchmark-local-gruntly":
            excluded[f.stem] += len(data)
            continue
        for r in data:
            if not isinstance(r, dict) or not r.get("task"):
                continue
            arm = r.get("arm") or r.get("mode") or ("local_alone" if "hidden_pass" in r else None)
            if arm is None:
                continue
            key = (r["task"], arm, r.get("rep"), r.get("cost_usd"), r.get("turns"), r.get("wall_s"), r.get("child_tokens"), r.get("hidden_pass", r.get("passed")))
            if key in seen:
                seen[key]["also_in"].append(f.stem)
                continue
            rec = {"row": r, "arm": arm, "exp": f.stem, "also_in": []}
            seen[key] = rec
            rows_raw.append(rec)

    # ---- 2. transcripts and persisted sessions ------------------------------------------------------------------------
    transcripts = defaultdict(list)           # stem -> [(dir, path, S)]
    for d in sorted(bench.glob("runs*")):
        if not d.is_dir():
            continue
        for p in d.glob("*.jsonl"):
            S = load_session(p)
            transcripts[p.stem].append((d.name, p, S))
    persisted = []                              # sessions in the persisted Claude Code logs of the benchmark workdirs
    if proj.exists():
        for d in proj.iterdir():
            n = d.name
            if not d.is_dir() or "gruntly-worktrees" in n:
                continue
            if "-Temp-bench-" in n or "-Temp-agentbench-" in n:
                for p in d.glob("*.jsonl"):
                    S = load_session(p)
                    if S["calls"]:
                        persisted.append(S)

    def sig(S):
        main = [c for c in S["calls"] if not c["side"]]
        return (sum(c["u"]["input_tokens"] for c in main), sum(c["u"]["cache_read_input_tokens"] for c in main),
                sum(c["u"]["cache_creation_input_tokens"] for c in main))
    persisted_by_sig = defaultdict(list)
    for S in persisted:
        persisted_by_sig[sig(S)].append(S)

    def total_cost(S):
        if S["result"]:
            return num(S["result"].get("total_cost_usd"))
        if S["cost_state"]:
            return num(S["cost_state"].get("totalCostUSD"))
        return None

    def find_session(row):
        stem = f"{row['task']}.{row.get('arm') or row.get('mode')}.{row.get('rep')}"
        cost = round(num(row.get("cost_usd")), 4)
        for dname, p, S in transcripts.get(stem, []):
            tc = total_cost(S)
            r = S["result"] or {}
            if tc is None or abs(round(tc, 4) - cost) > 0.00006 or r.get("num_turns") != row.get("turns"):
                continue
            tk = row.get("tokens")
            if tk and r.get("usage"):
                u = r["usage"]
                if (num(u.get("cache_read_input_tokens")) != tk.get("cache_read") or num(u.get("cache_creation_input_tokens")) != tk.get("cache_write")):
                    continue
            return S, "transcript", dname
        tk = row.get("tokens")
        if tk:
            cands = [S for S in persisted_by_sig.get((tk.get("input"), tk.get("cache_read"), tk.get("cache_write")), [])
                     if total_cost(S) is not None and abs(round(total_cost(S), 4) - cost) <= 0.00006]
            if len(cands) == 1:
                return cands[0], "persisted_session", None
        return None, "result_row_only", None

    # ---- 3. rows -----------------------------------------------------------------------------------------------------
    headers = {f.stem: md_header(f) for f in docs.glob("*.md")}
    metas = {}
    for f in docs.glob("*.meta.json"):
        m = read_json(f)
        if isinstance(m, list) and m:
            metas[f.stem[:-5]] = m[0]
    claude_versions = {m.get("claude") for m in metas.values() if m.get("claude")}

    out_rows = []
    timelines = []
    ttl_counter = Counter()
    gap_stats = []         # (run_id, delegated, max_gap)
    cache_expiry_events = []
    used_gdirs = 0

    for rec in rows_raw:
        row, arm_detail, exp = rec["row"], rec["arm"], rec["exp"]
        hdr = headers.get(exp, {})
        o = dict.fromkeys(COLUMNS)
        o["task_id"] = row["task"]
        o["task_type"] = "bug fix" if row["task"].startswith("click_") else TASK_TYPE.get(row["task"])   # click_*: fixes from the library's own history
        if o["task_type"] is None:
            notes["task_type"].append(row["task"])
        o["arm_detail"] = arm_detail
        o["experiment"] = exp
        o["rep"] = row.get("rep")
        o["run_id"] = f"{exp}.{row['task']}.{arm_detail}.{row.get('rep') if row.get('rep') is not None else 'na'}"
        is_local_alone = arm_detail == "local_alone"
        haiku_alone = (row.get("parent_model") == "haiku" or "haiku" in str(hdr.get("parent", ""))) and arm_detail in PARENT_ALONE_ARMS | {"haiku_alone"}
        if arm_detail == "haiku_alone" or (haiku_alone and arm_detail == "alone"):
            o["arm"] = "child_alone"
        elif is_local_alone:
            o["arm"] = "child_alone"
        elif arm_detail in PARENT_ALONE_ARMS:
            o["arm"] = "parent_alone"
        elif arm_detail in DELEGATED_ARMS:
            o["arm"] = "delegated"
        else:
            o["arm"] = arm_detail
            notes["arm"].append(arm_detail)

        # final outcome
        passed = row.get("passed", row.get("hidden_pass"))
        o["final_pass"] = passed if isinstance(passed, bool) else None
        o["wall_time_total_s"] = row.get("wall_s")

        S, source, dname = (None, "result_row_only", None) if is_local_alone else find_session(row)
        o["data_source"] = source
        A = analyse_session(S) if S else None
        res = (S or {}).get("result") or {}
        init = (S or {}).get("init") or {}

        # models and harness
        alias = row.get("parent_model") or None
        parent_model = A["parent_model"] if A else (ALIASES.get(alias) if alias else None)
        if not parent_model and hdr.get("parent") in ALIASES and not is_local_alone:
            parent_model = ALIASES[hdr["parent"]]            # the report header names the alias the run was started with
            notes["parent_model_from_report_header"].append(o["run_id"])
        if not parent_model and not is_local_alone and row.get("tokens") and "default" in str(hdr.get("parent", "")):
            tk = row["tokens"]
            cands = [m for m in PRICES if abs((price_call(m, tk["input"], tk["output"], tk["cache_read"], 0, tk["cache_write"]) or 9) - num(row.get("cost_usd"))) <= 0.0006]
            if len(cands) == 1:
                parent_model = cands[0]
                notes["parent_model_inferred_by_cost"].append(o["run_id"])
        if init.get("claude_code_version"):
            o["parent_harness"] = f"claude-code/{init['claude_code_version']}"
        elif not is_local_alone:
            o["parent_harness"] = "claude-code"
        delegated_arm = o["arm"] == "delegated"
        agent_model = parent_model
        o["parent_model"] = parent_model if o["arm"] != "child_alone" else None      # a child_alone run has no parent: its model is child_model

        # run date
        if S and S["first"]:
            o["run_date"] = S["first"].date().isoformat()
        else:
            o["run_date"] = hdr.get("date")

        # ---- parent / agent tokens
        mu = res.get("modelUsage") if res else None
        if not mu and S and S["cost_state"]:
            mu = S["cost_state"].get("modelUsage")
        tok = None
        tok_src = None
        if mu and agent_model in mu:
            v = mu[agent_model]
            tok = {"inp": num(v.get("inputTokens")), "out": num(v.get("outputTokens")), "cr": num(v.get("cacheReadInputTokens")),
                   "cw": num(v.get("cacheCreationInputTokens"))}
            tok_src = "model_usage"
        elif A and A["main"]:
            ct = [call_tokens(c) for c in A["main"]]
            tok = {k: sum(c[k] for c in ct) for k in ("inp", "out", "cr", "cw")}
            tok_src = "per_call_sum"
        elif row.get("tokens"):
            tk = row["tokens"]
            tok = {"inp": tk.get("input"), "out": tk.get("output"), "cr": tk.get("cache_read"), "cw": tk.get("cache_write")}
            tok_src = "result_row"
        o["parent_tokens_source"] = tok_src
        if A:
            o["output_tokens_reconcile"] = ("yes" if tok_src == "model_usage" and tok["out"] == sum(call_tokens(c)["out"] for c in A["main"]) else
                                            ("no (per-call output below reported total)" if tok_src == "model_usage" else "n/a"))
        turns = len(A["main"]) if A and A["main"] else row.get("turns")
        o["parent_turns"] = turns

        # ---- cost
        cost_models = {}
        if mu:
            for m, v in mu.items():
                cw_total = num(v.get("cacheCreationInputTokens"))
                w5 = 0
                if S:
                    w5 = sum(call_tokens(c)["w5"] for c in S["calls"] if c["model"] == m)
                w5 = min(w5, cw_total)
                pc = price_call(m, num(v.get("inputTokens")), num(v.get("outputTokens")), num(v.get("cacheReadInputTokens")), w5, cw_total - w5)
                if pc is not None:
                    pc += num(v.get("webSearchRequests")) * WEB_SEARCH_USD
                cost_models[m] = (pc, num(v.get("costUSD")))
        reported = None
        if res:
            reported = num(res.get("total_cost_usd"))
        elif S and S["cost_state"]:
            reported = num(S["cost_state"].get("totalCostUSD"))
        elif row.get("cost_usd") is not None:
            reported = row["cost_usd"]
        computed = None
        if cost_models and all(v[0] is not None for v in cost_models.values()):
            computed = sum(v[0] for v in cost_models.values())
        elif tok and agent_model in PRICES and tok_src == "result_row":
            computed = price_call(agent_model, tok["inp"], tok["out"], tok["cr"], 0, tok["cw"])      # no 5m/1h split recorded: all writes at the 1h rate
            notes["cost_all_writes_1h"].append(o["run_id"])
        if tok_src == "result_row" and computed is not None and reported is not None and abs(computed - reported) > 0.0005:
            # the row's token totals come from the last session's usage only (the run was split over sessions); they cannot price to the reported cost
            notes["row_tokens_incomplete"].append(o["run_id"])
            computed, tok, tok_src = None, None, "result_row (incomplete: tokens do not price to the reported cost)"
            o["parent_tokens_source"] = tok_src
        o["cost_usd_computed"] = round(computed, 6) if computed is not None else None
        o["cost_usd_reported"] = round(reported, 6) if reported is not None else None
        if computed is not None and reported is not None:
            o["cost_diff_usd"] = round(computed - reported, 6)
        other = [m for m in cost_models if m != agent_model]
        o["other_models_cost_usd_reported"] = round(sum(cost_models[m][1] for m in other), 6) if other else (0.0 if cost_models else None)

        # ---- gruntly records (child side)
        gstat = row.get("gruntly_status") or []
        o["gruntly_status"] = "|".join(gstat) if gstat else None
        o["gruntly_attempts"] = sum(row.get("gruntly_attempts") or []) if row.get("gruntly_attempts") else None
        gdirs = []
        if dname and delegated_arm:
            gd = bench / dname / f"{row['task']}.{arm_detail}.{row.get('rep')}.gruntly"
            if gd.exists():
                gdirs = sorted(p for p in gd.glob("r_*") if p.is_dir())
        recs = []
        for g in gdirs:
            rr = read_json(g / "result.json") or {}
            spec = read_json(g / "spec.json") or {}
            cu = read_json(g / "child_usage.json") or {}
            tr = read_json(g / "trace.json") or {}
            lg = parse_child_log(g / "child.log")
            recs.append({"res": rr, "spec": spec, "cu": cu, "tr": tr, "log": lg})
        if recs:
            tot_tokens = sum(num(r["cu"].get("tokens")) or num(r["res"].get("child_tokens")) for r in recs)
            if row.get("child_tokens") not in (None, tot_tokens):
                notes["gruntly_dir_mismatch"].append(o["run_id"])
                recs = []
            else:
                used_gdirs += 1
        # harness / model / runtime
        ch = cm = prov = endpoint = None
        if delegated_arm or o["arm"] == "child_alone":
            if recs:
                spec = recs[-1]["spec"]
                ch, cm, prov, endpoint = spec.get("harness"), spec.get("model"), spec.get("provider"), spec.get("endpoint")
            if not ch:
                ch = row.get("child_harness") or (hdr.get("child_harness") if delegated_arm else None)
                cm = row.get("child_model") or (hdr.get("child_model") if delegated_arm else None)
            if arm_detail == "subagent":
                ch = "claude-code-subagent"
            if o["arm"] == "child_alone":
                ch, cm = ("claude-code", agent_model) if not is_local_alone else (hdr.get("child_harness") or "opencode", hdr.get("child_model") or "qwen/qwen3.5-9b")
        o["child_harness"], o["child_model"] = ch, cm
        o["child_runtime"] = ("anthropic api (claude code cli)" if o["arm"] == "child_alone" and not is_local_alone else child_runtime(ch, cm, prov, endpoint)) if ch else None
        if cm and re.search(r"qwen3\.5-9b", cm) and (o["child_runtime"] or "").startswith("lm studio"):
            o["quantization"] = "Q4_K_M"       # from the LM Studio server logs' model list
        if ch and o["child_runtime"] and o["child_runtime"].startswith("lm studio") and hdr.get("ctx"):
            o["child_context_window"] = hdr["ctx"]
        elif ch and o["child_runtime"] and "anthropic" in o["child_runtime"]:
            o["child_context_window"] = None

        # ---- tokens: agent (parent) vs child
        if o["arm"] == "child_alone" and not is_local_alone:
            o["child_input_tokens"] = (tok["inp"] + tok["cr"] + tok["cw"]) if tok else None
            o["child_output_tokens"] = tok["out"] if tok else None
            o["child_tokens_total"] = (o["child_input_tokens"] + o["child_output_tokens"]) if tok else None
            o["child_turns"] = turns
            o["child_tokens_source"] = tok_src
        elif is_local_alone:
            o["child_tokens_total"] = row.get("child_tokens")
            o["child_turns"] = row.get("requests")
            o["child_tokens_source"] = "result_row"
            o["tests_passed_after_child"] = row.get("visible_pass") if isinstance(row.get("visible_pass"), bool) else None
            o["cost_usd_computed"] = o["cost_usd_reported"] = 0.0
            o["child_claimed_success"] = None
        else:
            if tok:
                o["parent_uncached_input"], o["parent_cache_read"], o["parent_cache_write"], o["parent_output"] = tok["inp"], tok["cr"], tok["cw"], tok["out"]
        if delegated_arm:
            if arm_detail == "subagent" and mu:
                sm = [m for m in mu if m != agent_model]
                if sm:
                    v = mu[sm[0]]
                    o["child_input_tokens"] = num(v.get("inputTokens")) + num(v.get("cacheReadInputTokens")) + num(v.get("cacheCreationInputTokens"))
                    o["child_output_tokens"] = num(v.get("outputTokens"))
                    o["child_tokens_total"] = o["child_input_tokens"] + o["child_output_tokens"]
                    o["child_model"] = sm[0]
                    o["child_turns"] = len([c for c in A["side"]]) if A else None
                    o["child_tokens_source"] = "model_usage"
                    o["child_cost_usd_reported"] = round(cost_models[sm[0]][1], 6)
                    o["child_cost_usd_computed"] = round(cost_models[sm[0]][0], 6) if cost_models[sm[0]][0] is not None else None
            elif recs:
                lg_tot = sum(r["log"]["inp"] + r["log"]["out"] for r in recs)
                tok_tot = sum(num(r["cu"].get("tokens")) for r in recs)
                if ch == "claude" and lg_tot == tok_tot and lg_tot:
                    o["child_input_tokens"] = sum(r["log"]["inp"] for r in recs)
                    o["child_output_tokens"] = sum(r["log"]["out"] for r in recs)
                    o["child_tokens_source"] = "child.log (matches gruntly total)"
                o["child_tokens_total"] = tok_tot or row.get("child_tokens")
                o["child_turns"] = sum(num(r["cu"].get("requests")) for r in recs) or None
                o["child_wall_s"] = sum(num(r["res"].get("wall_s")) for r in recs)
                cr = sum(num(r["cu"].get("cost_usd")) for r in recs)
                if ch == "claude":
                    o["child_cost_usd_reported"] = round(cr, 6)
                    comp = 0.0
                    ok = True
                    for r in recs:
                        for mname, a in r["log"]["mu"].items():
                            # modelUsage carries the TTL split per model for the whole session; the result event's `usage` only has the last turn's, which priced
                            # every cache write at the 1-hour rate and overshot the reported cost by 2.7% over the Claude children (fixed 2026-11-13).
                            w5 = min(a[6], a[3]) if (a[6] + a[7]) else (min(r["log"]["w5"], a[3]) if len(r["log"]["mu"]) == 1 else 0)
                            pc = price_call(mname, a[0], a[1], a[2], w5, a[3] - w5)
                            if pc is None:
                                ok = False
                            else:
                                comp += pc + a[4] * WEB_SEARCH_USD
                    o["child_cost_usd_computed"] = round(comp, 6) if ok else None
                else:
                    o["child_cost_usd_reported"] = 0.0 if (prov in (None, "local") and ch in ("opencode", "qwen", "generic")) else None
            else:
                if row.get("child_tokens"):
                    o["child_tokens_total"] = row["child_tokens"]
                    o["child_tokens_source"] = "result_row"
                if row.get("child_cost_usd") is not None and ch == "claude":
                    o["child_cost_usd_reported"] = row["child_cost_usd"]
                o["child_wall_s"] = row.get("gruntly_wall_s")
        if delegated_arm and not o.get("child_wall_s") and row.get("gruntly"):
            o["child_wall_s"] = sum(num(g.get("wall_s")) for g in row["gruntly"])

        # ---- delegation behaviour from the parent's tool calls
        occurred = None
        if delegated_arm:
            if arm_detail == "subagent":
                occurred = bool(A and A["side"]) if A else None
            elif gstat:
                occurred = True
            elif A is not None:
                occurred = bool(A["starts"])
            else:
                occurred = bool(row.get("gruntly_status")) if "gruntly_status" in row else None
        o["delegation_occurred"] = occurred
        if A and delegated_arm and occurred:
            o["brief_chars"] = A["brief_chars"]
            o["brief_tokens"] = math.ceil(A["brief_chars"] / 4) if A["brief_chars"] else None
            o["rebrief_count"] = A["rebrief"]
            o["parent_idle_s_while_child_ran"] = round(A["idle"], 1) if A["idle"] is not None else None
            if A["issue_idx"] is not None:
                has_inspect = any(k == "inspect" for _, k in A["verif"])
                o["verification_method"] = "LLM review" if (has_inspect or num(row.get("reviewer_cost_usd")) > 0) else "tests only"
                o["verification_tokens"] = A["vtok"] if A["verif"] else 0
                if A["takeover_idx"] is None:
                    o["takeover"] = "none"
                else:
                    partial = any(row.get("gruntly_applied") or []) or A["applied_before"]
                    o["takeover"] = "from_child_partial_work" if partial else "from_scratch"
                    ct = [call_tokens(c) for c in A["main"][A["takeover_idx"]:]]
                    o["parent_tokens_after_takeover"] = sum(c["inp"] + c["out"] + c["cr"] + c["cw"] for c in ct)
                    cc = [price_call(A["main"][A["takeover_idx"] + j]["model"], c["inp"], c["out"], c["cr"], c["w5"], c["w1"]) for j, c in enumerate(ct)]
                    o["parent_cost_after_takeover_usd"] = round(sum(x for x in cc if x is not None), 6) if all(x is not None for x in cc) else None
            else:
                o["takeover"] = "none" if not row.get("takeover_edits") else "from_scratch"
        elif delegated_arm and occurred and row.get("takeover_edits") is not None:
            o["takeover"] = "none" if not row["takeover_edits"] else None
            if row["takeover_edits"]:
                notes["takeover_untyped_no_transcript"].append(o["run_id"])
        if A:
            o["max_gap_between_parent_api_calls_s"] = round(A["max_gap"], 1) if A["max_gap"] is not None else None
            if not o["wall_time_total_s"] and S["first"] and S["last"]:
                o["wall_time_total_s"] = round((S["last"] - S["first"]).total_seconds())
            ttl = Counter()
            for c in A["main"]:
                ct = call_tokens(c)
                if ct["w1"]:
                    ttl["1h"] += 1
                if ct["w5"]:
                    ttl["5m"] += 1
            o["cache_ttl_main_thread"] = "+".join(sorted(ttl)) if ttl else None
            if delegated_arm and occurred:
                gap_stats.append(A["gaps"])
            # cache-expiry events: a call after a long gap that re-wrote the context instead of reading it
            for i, c in enumerate(A["main"]):
                if i == 0:
                    continue
                gap = A["gaps"][i - 1] if i - 1 < len(A["gaps"]) else None
                ct = call_tokens(c)
                prev = call_tokens(A["main"][i - 1])
                if gap is not None and gap >= 60:
                    cache_expiry_events.append({"run": o["run_id"], "gap": gap, "cr": ct["cr"], "prev_ctx": prev["cr"] + prev["cw"] + prev["inp"],
                                                "cw": ct["cw"], "label": A["labels"][i], "delegated": bool(delegated_arm and occurred)})

        # ---- outcome of the child and failure reason
        last_status = gstat[-1] if gstat else None
        if delegated_arm and occurred and arm_detail != "subagent":
            if last_status in ("passed", "escalate"):
                o["child_claimed_success"] = True
            elif last_status in ("timeout", "error"):
                o["child_claimed_success"] = False
            if recs and recs[-1]["res"].get("gates") is not None:
                o["tests_passed_after_child"] = bool(recs[-1]["res"]["gates"].get("acceptance"))
            elif last_status in ("passed",):
                o["tests_passed_after_child"] = True
            elif last_status in ("escalate",):
                o["tests_passed_after_child"] = False
            reason = None
            if last_status == "timeout":
                reason = "timeout"
            elif last_status == "error":
                reason = "other"
                if recs and re.search(r"context", " ".join(str(r["res"].get(k)) for k in ("failure_bundle",)), re.I):
                    reason = "context overflow"
            elif last_status == "escalate":
                files = None
                if recs:
                    files = (recs[-1]["res"].get("diff_stat") or {}).get("files")
                reason = "gave up" if files == 0 else "wrong fix"
            elif last_status == "passed" and o["final_pass"] is False:
                reason = "falsely claimed success"
            o["failure_reason"] = reason
        # parent-alone/child-alone: no child failure reason by definition

        out_rows.append(o)

        # ---- timeline candidates
        if A and delegated_arm and occurred and A["main"]:
            timelines.append((o, A, S))

    # ---- 4. timeline sample ------------------------------------------------------------------------------------------
    def pick(group, n):
        cand = [t for t in timelines if t[0]["tests_passed_after_child"] is not None]
        if group == "success":
            cand = [t for t in cand if t[0]["final_pass"] is True and t[0]["takeover"] == "none"]
        else:
            cand = [t for t in cand if t[0]["final_pass"] is False or t[0]["takeover"] not in (None, "none")]
        # most informative first: the longest gap between parent calls, then the most parent calls; ties by run id
        cand.sort(key=lambda t: (-(t[1]["max_gap"] or 0), -len(t[1]["main"]), t[0]["run_id"]))
        return cand[:n]
    tl_rows = []
    chosen = []
    for group in ("success", "failed"):
        for o, A, S in pick(group, 5):
            chosen.append((group, o["run_id"]))
            start = S["first"]
            prev_last = None
            for i, c in enumerate(A["main"]):
                ct = call_tokens(c)
                gap = (c["first"] - prev_last).total_seconds() if prev_last and c["first"] else None
                tl_rows.append({"run_id": o["run_id"], "outcome_group": group, "call_index": i + 1,
                                "timestamp_utc": c["first"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" if c["first"] else None,
                                "seconds_since_run_start": round((c["first"] - start).total_seconds(), 1) if c["first"] and start else None,
                                "gap_since_prev_call_s": round(gap, 1) if gap is not None else None,
                                "uncached_input": ct["inp"], "cache_read": ct["cr"], "cache_write": ct["cw"], "output": ct["out"],
                                "label": A["labels"][i]})
                prev_last = c["last"]

    write_outputs(out, out_rows, tl_rows, chosen, notes, excluded, cache_expiry_events, gap_stats, used_gdirs, claude_versions, rec_count=len(rows_raw))


def write_outputs(out, rows, tl_rows, chosen, notes, excluded, cache_events, gap_stats, used_gdirs, claude_versions, rec_count):
    out.mkdir(parents=True, exist_ok=True)
    with (out / "runs.csv").open("w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    with (out / "timeline_sample.csv").open("w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=TIMELINE_COLUMNS)
        w.writeheader()
        for r in tl_rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    (out / "_stats.json").write_text(json.dumps({"rows": len(rows)}), encoding="utf8")
    write_readme(out, rows, tl_rows, chosen, notes, excluded, cache_events, gap_stats, used_gdirs, claude_versions)


# README ---------------------------------------------------------------------------------------------------------------
def fmt(x, nd=4):
    return "-" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def write_readme(out, rows, tl_rows, chosen, notes, excluded, cache_events, gap_stats, used_gdirs, claude_versions):
    L = []
    A = L.append
    n = len(rows)
    by_src = Counter(r["data_source"] for r in rows)
    A("# Delegation export\n")
    A(f"Generated by `bench/delegation_export.py` (stdlib only, read-only on the repo and on the Claude Code logs). {n} runs, one row per task per arm per repetition. "
      "Numbers and short labels only: no prompts, code, transcripts, paths, keys or environment.\n")
    A("## Sources used\n")
    A("| source | what it gave | runs that use it |\n|---|---|---|")
    A(f"| benchmark result files (`docs/benchmarks/*.json`, 2026-11-07 to 2026-11-12) | task, arm, repetition, hidden-test pass, wall time, Claude Code's reported cost and turns, token totals, gruntly status/attempts, child token total | {n} (every row) |")
    A(f"| per-run stream-json transcripts (`bench/runs*/<task>.<arm>.<rep>.jsonl`), matched to a result row by task.arm.rep + reported cost + turn count + cache token totals | per-API-call usage and timestamps, tool calls, model usage per model, init (Claude Code version) | {by_src.get('transcript', 0)} |")
    A(f"| persisted Claude Code session logs of the benchmark work directories (`~/.claude/projects/*bench*`), matched by cache token totals + reported cost (unique match only) | the same per-call data for runs whose transcript file was overwritten by a later run | {by_src.get('persisted_session', 0)} |")
    A(f"| gruntly run records (`<run>.gruntly/r_*/`: `result.json`, `spec.json`, `child_usage.json`, `trace.json`, `child.log`), kept only by runs after 2026-11-12 | child tokens in/out, child turns, child cost, harness/model/provider, gate results | {used_gdirs} |")
    A("| run-report headers (`docs/benchmarks/*.md`) | child harness, child model, context window, parent model and run date for runs whose row does not carry them | most pre-11-12 delegated rows |")
    A("| LM Studio server logs (`~/.lmstudio/server-logs`) | quantization (Q4_K_M) and the loaded context sizes | local-model rows (see gaps) |")
    A(f"| not used, no parent model: {', '.join(f'`{k}` ({v} rows)' for k, v in excluded.items())} | child-only experiments (gruntly or the child on its own with no Claude parent) | 0 |")
    A(f"\nResult rows found: {n} after removing duplicates (a run saved into more than one result file is counted once). Claude Code versions seen in run metadata: {', '.join(sorted(claude_versions)) or 'n/a'}.\n")
    A("Experiments (result file -> arms, children): ")
    exp = defaultdict(lambda: Counter())
    for r in rows:
        exp[r["experiment"]][f"{r['arm_detail']}"] += 1
    for k, v in sorted(exp.items()):
        ch = Counter((r["child_harness"], r["child_model"]) for r in rows if r["experiment"] == k and r["arm"] == "delegated" and r["child_model"])
        A(f"- `{k}`: " + ", ".join(f"{a} x{b}" for a, b in sorted(v.items())) + (f"; child {', '.join(f'{h}/{m}' for (h, m) in ch)}" if ch else ""))
    A("")
    A("## Columns: how each was derived\n")
    A("Blank = could not be computed from the data (see Gaps). One row per run; `arm` is parent_alone / delegated / child_alone, `arm_detail` is the benchmark's own arm label (alone, lean_alone, forced, policy, gd, gdA, gdAB, lean, planner, subagent, gruntly, haiku_alone, local_alone), `delegation_occurred` says whether gruntly (or the sub-agent) was actually used (policy and gd arms often were not).\n")
    cols = [
        ("run_id, task_id, rep, experiment", "result file stem + task + arm label + repetition."),
        ("task_type", "by hand from each task's first sentence: bug fix / bulk edit (rename everywhere) / refactor / read-heavy (reading, fetching, researching, summarising) / other (new function, feature, data wrangling)."),
        ("parent_harness", "Claude Code, version from the transcript's init event when available."),
        ("parent_model", "model of the main-thread API calls in the transcript; else the row's alias; else (the 11-07 'default model' runs) the only model whose price table reproduces the reported cost."),
        ("child_harness, child_model", "gruntly's `spec.json` when kept, else the row's fields, else the result-report header. For `child_alone` rows with Claude Code the child is Claude Code running Haiku with no parent; for sub-agent rows it is Claude Code's own sub-agent (model from the usage record)."),
        ("child_runtime", "anthropic api (Claude CLI child); LM Studio (llama.cpp) for local `qwen/...` models; NVIDIA-hosted API for `nvidia/`, `poolside/`, `deepseek-ai/` models run through Hermes (inferred from the model id; the logs do not record the host)."),
        ("quantization", "Q4_K_M for the local Qwen3.5-9B (LM Studio logs); blank elsewhere (hosted models do not report it)."),
        ("child_context_window", "tokens, from the result-report header (the context gruntly required, 32k); the loaded sizes vary in the LM Studio logs (4k to 32k), so treat as the configured minimum."),
        ("parent_uncached_input, parent_cache_read, parent_cache_write, parent_output", "Claude Code's per-model usage (`modelUsage`) for the parent model; falls back to the sum of per-call usage, then to the result row's totals (`parent_tokens_source`). Blank for child_alone rows, whose tokens are in the child_* columns."),
        ("parent_turns", "distinct API calls on the main thread (transcript); else the reported `num_turns`."),
        ("child_input_tokens, child_output_tokens", "input = uncached + cache read + cache write; Claude child: summed from its stream-json result lines (kept only when the sum equals gruntly's own total); sub-agent: its `modelUsage` entry; Claude Code Haiku alone: the session's usage. Blank for OpenCode/Hermes children (gruntly records one total, no split)."),
        ("child_tokens_total, child_turns", "gruntly's `child_usage.json` (tokens, requests) or the result row's `child_tokens`; child_turns blank where only the total was kept."),
        ("brief_chars, brief_tokens", "length of the Bash command that started the first gruntly run (the work order the parent wrote, incl. flags); tokens = ceil(chars/4), an estimate (no tokenizer). Blank when gruntly ran outside the session (gd) or no transcript."),
        ("verification_method, verification_tokens", "after the child returned and before any takeover: 'LLM review' if the parent read the diff or files (Read/Grep/Glob, `gruntly diff`, `git diff`) or a reviewer model was used, else 'tests only' (gruntly's gates). Tokens = for each such parent call, its output + the uncached input and cache write of the next call (the tool result entering context); re-running tests counts as tests."),
        ("child_claimed_success", "proxy: the child finished normally and returned a result (gruntly status passed or escalate). Its own words are not exported. False for timeout/error."),
        ("tests_passed_after_child", "gruntly's acceptance gate after the last attempt (visible tests). local_alone: the visible-test flag."),
        ("final_pass", "hidden tests (never shown to parent or child) pass on the final tree, from the benchmark judge."),
        ("rebrief_count", "extra gruntly runs after the first plus `continue` calls, counted from the parent's tool calls."),
        ("gruntly_attempts, gruntly_status", "from the result row (sum of attempts; statuses joined by `|`)."),
        ("takeover", "none = no parent edit after delegating. A takeover is the parent editing files itself after it delegated (Edit/Write/MultiEdit/NotebookEdit, or a Bash/PowerShell write: sed -i, tee, Set-Content, git apply...). from_child_partial_work = the child's changes were in the working tree first (gruntly applied them, or the parent ran `gruntly apply`); from_scratch = otherwise."),
        ("parent_tokens_after_takeover, parent_cost_after_takeover_usd", "all four token kinds / dollars of the parent calls from the first takeover call to the end."),
        ("wall_time_total_s", "whole session wall time as the runner measured it."),
        ("child_wall_s", "gruntly's own wall time for the child (sum over its runs)."),
        ("parent_idle_s_while_child_ran", "sum over the parent's blocking gruntly tool calls (start, continue, wait) of tool-result time minus tool-call time."),
        ("max_gap_between_parent_api_calls_s", "largest gap between the last streamed block of one main-thread API call and the first block of the next (includes tool time and the next call's time to first token)."),
        ("failure_reason", "delegated rows where the child failed: timeout (gruntly status timeout); gave up (escalate with an empty diff); wrong fix (escalate: visible tests still failing after the retries); falsely claimed success (gruntly reported passed, hidden tests failed); other (status error: child process or connection error; reasons are not recorded). tool-call error, unfinished and context overflow never occur in the recorded statuses."),
        ("cost_usd_computed", "tokens x the price table below for every model in the session (parent plus any sub-agent models), with cache writes split 5-minute/1-hour from per-call usage, plus web-search fees; for 11 rows without a transcript from the result row's token totals with all writes at the 1-hour rate."),
        ("cost_usd_reported", "Claude Code's `total_cost_usd` for the session (what /cost shows): parent plus sub-agents, not a gruntly Claude child."),
        ("child_cost_usd_computed / _reported", "Claude child only: tokens x price table / the CLI's own cost per attempt. Local and hosted free-tier children: 0.0 reported where the child is local, blank where hosted (no dollar figure recorded)."),
        ("other_models_cost_usd_reported", "reported cost of models other than the parent's in the session (Haiku sub-agents such as web-fetch, or the sub-agent child)."),
        ("data_source, parent_tokens_source, child_tokens_source, output_tokens_reconcile, cache_ttl_main_thread", "provenance flags. `output_tokens_reconcile` = no means the per-call output counts in the transcript sum to less than the reported output total (streamed snapshots), so per-call output in the timeline is a lower bound. `cache_ttl_main_thread` = which cache-write TTLs the main thread used (1h)."),
    ]
    for a, b in cols:
        A(f"- **{a}**: {b}")
    A("")
    A("## Price table ($ per million tokens)\n")
    A("| model | input | output | cache read | cache write 5 min | cache write 1 h |\n|---|---|---|---|---|---|")
    for m, p in PRICES.items():
        A(f"| {m} | {p['inp']} | {p['out']} | {p['read']} | {p['w5']} | {p['w1']} |")
    A(f"\nWeb search: ${WEB_SEARCH_USD} per request. Rates fitted from Claude Code's own per-model `costUSD` in these runs: Sonnet 5.5 and Opus 5.5 reproduce it exactly (222 and 29 records, zero residual), Haiku 5.5 reproduces it once web search is priced and the 5-minute write rate is used for sub-agents (verified on 4 runs). The 5-minute write rate for Sonnet/Opus is the 1.25x-input pattern, unverified (the main thread always wrote 1-hour caches, and no Sonnet/Opus 5-minute write occurs in these runs). API-equivalent dollars: a Claude subscription is not billed per token.\n")
    A("## Definition of takeover\n")
    A("The parent edits files itself after it has delegated (any Edit/Write/MultiEdit/NotebookEdit call, or a Bash/PowerShell write command, after the first gruntly start call). `none`: no such edit. `from_child_partial_work`: the child's changes were applied to the working tree before the first parent edit. `from_scratch`: they were not (the child's diff was left in its worktree or discarded). Detected from the parent's tool calls, so it needs a transcript; rows without one are blank.\n")
    # counts per arm and outcome
    A("## Task counts per arm and outcome\n")
    A("| arm | runs | final pass | final fail | pass unknown | delegation occurred |\n|---|---|---|---|---|---|")
    for arm in ("parent_alone", "delegated", "child_alone"):
        rr = [r for r in rows if r["arm"] == arm]
        p = sum(1 for r in rr if r["final_pass"] is True)
        f = sum(1 for r in rr if r["final_pass"] is False)
        u = len(rr) - p - f
        d = sum(1 for r in rr if r["delegation_occurred"] is True)
        A(f"| {arm} | {len(rr)} | {p} | {f} | {u} | {d if arm == 'delegated' else '-'} |")
    A("")
    A("Delegated runs by what happened to the child:\n")
    c = Counter((r["delegation_occurred"], r["failure_reason"] or ("passed" if r["final_pass"] else "n/a"), r["takeover"] or "-") for r in rows if r["arm"] == "delegated")
    A("| delegation occurred | outcome / failure reason | takeover | runs |\n|---|---|---|---|")
    for k, v in sorted(c.items(), key=lambda x: str(x[0])):
        A(f"| {k[0]} | {k[1]} | {k[2]} | {v} |")
    A("")
    # preliminary table
    A("## Preliminary table: parent cost and pass rate per arm\n")
    A("Means and medians of `cost_usd_reported` (the Claude Code session: parent plus its sub-agents, **excluding** a gruntly Claude child, whose reported cost is in the next column), by arm and agent model. Models are separated because they differ by 5x to 40x in price, and the experiments are not matched designs: different task sets and repetitions per file, so read within a row group, not across them. The `+child $` column adds the Claude child's reported cost (mean).\n")
    A("| arm | parent model | runs | pass rate | mean $ | median $ | mean +child $ | mean turns | mean wall s |\n|---|---|---|---|---|---|---|---|---|")
    groups = defaultdict(list)
    for r in rows:
        if r["arm"] == "child_alone" and r["experiment"] == "benchmark-local-alone":
            continue
        groups[(r["arm"], r["parent_model"] or (f"({r['child_model']}, no parent)" if r["arm"] == "child_alone" else "unknown"))].append(r)
    for (arm, pm), rr in sorted(groups.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        costs = [r["cost_usd_reported"] for r in rr if r["cost_usd_reported"] is not None]
        wc = [r["cost_usd_reported"] + (r["child_cost_usd_reported"] or 0) for r in rr if r["cost_usd_reported"] is not None]
        pa = [r["final_pass"] for r in rr if r["final_pass"] is not None]
        turns = [r["parent_turns"] for r in rr if isinstance(r["parent_turns"], (int, float))]
        wall = [r["wall_time_total_s"] for r in rr if isinstance(r["wall_time_total_s"], (int, float))]
        A(f"| {arm} | {pm or 'unknown'} | {len(rr)} | {fmt(sum(pa)/len(pa)*100 if pa else None, 0)}% | {fmt(statistics.mean(costs) if costs else None)} | {fmt(statistics.median(costs) if costs else None)} | "
          f"{fmt(statistics.mean(wc) if wc else None)} | {fmt(statistics.mean(turns) if turns else None, 1)} | {fmt(statistics.mean(wall) if wall else None, 0)} |")
    A("")
    # delegated vs not within delegated
    A("Delegated arms split by whether delegation actually occurred (Sonnet parent only):\n")
    A("| arm label | delegation occurred | runs | pass rate | mean $ | median $ |\n|---|---|---|---|---|---|")
    g2 = defaultdict(list)
    for r in rows:
        if r["arm"] == "delegated" and r["parent_model"] == "claude-sonnet-5-5":
            g2[(r["arm_detail"], r["delegation_occurred"])].append(r)
    for (a_, d_), rr in sorted(g2.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        costs = [r["cost_usd_reported"] for r in rr if r["cost_usd_reported"] is not None]
        pa = [r["final_pass"] for r in rr if r["final_pass"] is not None]
        A(f"| {a_} | {d_} | {len(rr)} | {fmt(sum(pa)/len(pa)*100 if pa else None, 0)}% | {fmt(statistics.mean(costs) if costs else None)} | {fmt(statistics.median(costs) if costs else None)} |")
    A("")
    # cache check
    A("## Does the cache expire while the child runs?\n")
    deleg = [e for e in cache_events if e["delegated"]]
    allg = [g for gs in gap_stats for g in gs]
    A(f"Main-thread cache writes are all 1-hour TTL (`cache_ttl_main_thread`); only Claude Code's own sub-agents write 5-minute caches. Across {len(gap_stats)} delegated runs with timestamps there are {len(allg)} gaps between consecutive parent API calls; "
      f"longest {max(allg) if allg else 0:.0f} s, {sum(1 for g in allg if g >= 300)} gaps >= 300 s, {sum(1 for g in allg if g >= 3600)} gaps >= 3600 s.\n")
    A("Calls that follow a gap of at least 60 s (all delegated runs), and whether they read the cache or re-wrote the context:\n")
    A("| gap bucket | calls | with cache read > 0 | re-wrote context (cache read = 0) |\n|---|---|---|---|")
    for lo, hi, name in ((60, 300, "60-300 s"), (300, 900, "300-900 s"), (900, 3600, "900-3600 s"), (3600, 10**9, ">= 3600 s")):
        ee = [e for e in deleg if lo <= e["gap"] < hi]
        A(f"| {name} | {len(ee)} | {sum(1 for e in ee if e['cr'] > 0)} | {sum(1 for e in ee if e['cr'] == 0)} |")
    A("")
    A("`timeline_sample.csv`: " + f"{len(set(c[1] for c in chosen))} delegated runs ({sum(1 for c in chosen if c[0]=='success')} successful with no takeover, {sum(1 for c in chosen if c[0]=='failed')} failed or taken over), one row per parent API call. "
      "Selection rule: of the delegated runs with a transcript, those with the longest gap between parent calls first (to give the cache the best chance to expire), so the sample is biased toward slow runs; the unbiased counts are the gap table above. "
      "Labels: before_delegation (calls up to and including the one that issues the first gruntly call), during (a parent call made while a gruntly call was running), after_child_returned, takeover (from the first parent edit onward). `cache_write` is the 5-minute plus 1-hour writes; `output` is the per-call output count (a lower bound where `output_tokens_reconcile` is 'no').\n")
    # reconciliation
    A("## Reconciliation of computed vs reported cost\n")
    both = [r for r in rows if r["cost_usd_computed"] is not None and r["cost_usd_reported"] is not None and r["cost_diff_usd"] is not None]
    sc, sr = sum(r["cost_usd_computed"] for r in both), sum(r["cost_usd_reported"] for r in both)
    diffs = [abs(r["cost_diff_usd"]) for r in both]
    off = [r for r in both if abs(r["cost_diff_usd"]) > 0.0005]
    A(f"{len(both)} rows have both. Computed total ${sc:.4f}, reported total ${sr:.4f}, difference ${sc - sr:+.4f} ({(sc - sr) / sr * 100 if sr else 0:+.3f}%). "
      f"Largest single-row difference ${max(diffs) if diffs else 0:.4f}; {len(off)} rows differ by more than $0.0005.")
    if off:
        by = Counter((r["data_source"], r["parent_tokens_source"], r["parent_model"]) for r in off)
        A("Rows over $0.0005: " + "; ".join(f"{k[0]}/{k[1]}/{k[2]}: {v}" for k, v in by.items()) + ".")
    ch = [r for r in rows if r["child_cost_usd_computed"] is not None and r["child_cost_usd_reported"] is not None]
    if ch:
        A(f"Claude children: computed ${sum(r['child_cost_usd_computed'] for r in ch):.4f} vs reported ${sum(r['child_cost_usd_reported'] for r in ch):.4f} over {len(ch)} rows.")
    A("")
    # gaps
    A("## Gaps: fields that could not be filled\n")
    reasons = {
        "parent_model": "no transcript or persisted session and the result row carries no model.",
        "child_harness": "arm without a child (parent_alone) or no record of the child's harness.",
        "child_model": "same as child_harness.",
        "child_runtime": "no child, or the harness/model combination could not be classified.",
        "quantization": "recorded only for the local Qwen3.5-9B (LM Studio logs); hosted models (NVIDIA, Anthropic) do not report one; parent_alone rows have no child.",
        "child_context_window": "recorded only as the report header's 32k for local children; hosted/Anthropic children have no configured window in the data.",
        "parent_uncached_input": "child_alone rows (tokens are in child_*) and rows with no token data.",
        "child_input_tokens": "OpenCode/Hermes children: gruntly stored one total (`child_tokens`) and the child CLIs' own logs (OpenCode database, Hermes) no longer hold the runs; LM Studio logs hold raw prompts per request but cannot be tied to a run without guessing at time windows, so they are not used.",
        "child_output_tokens": "same as child_input_tokens.",
        "child_tokens_total": "parent_alone rows have no child; policy/gd rows where delegation did not occur; hosted-child rows whose result recorded no total.",
        "child_turns": "recorded only where gruntly's `child_usage.json` was kept (runs from 2026-11-12) and for the local-alone run (requests).",
        "brief_tokens": "needs a transcript with a visible gruntly call; the gd arm ran gruntly outside the session; estimated at 4 chars/token.",
        "brief_chars": "same as brief_tokens.",
        "verification_method": "needs a transcript and a delegation.",
        "verification_tokens": "same as verification_method.",
        "child_claimed_success": "the child's own claim is not exported; proxy only for delegated rows with a gruntly status.",
        "tests_passed_after_child": "delegated rows with a gruntly status only (and local-alone).",
        "final_pass": "rows whose result record has no judge outcome.",
        "rebrief_count": "needs a transcript with gruntly calls.",
        "gruntly_attempts": "no gruntly run.",
        "gruntly_status": "no gruntly run.",
        "takeover": "needs a transcript (or the row's takeover_edits count, which only gives 'none').",
        "parent_tokens_after_takeover": "only when a takeover occurred and a transcript exists.",
        "parent_cost_after_takeover_usd": "same.",
        "child_wall_s": "no gruntly run, or the result row recorded no gruntly wall time.",
        "parent_idle_s_while_child_ran": "needs a transcript and a blocking gruntly call (gd runs gruntly outside the session).",
        "max_gap_between_parent_api_calls_s": "needs timestamps: runs with no transcript or persisted session, and single-call runs.",
        "failure_reason": "blank when the child did not fail, or when no child ran.",
        "cost_usd_computed": "no token data or an unknown model.",
        "cost_usd_reported": "no cost recorded (local_alone).",
        "child_cost_usd_computed": "only Claude children (the others have no dollar price here).",
        "child_cost_usd_reported": "hosted free-tier children report no dollars; local children are 0.0.",
        "parent_cost_after_takeover_usd": "only when a takeover occurred.",
        "cache_ttl_main_thread": "needs per-call usage with the TTL split.",
        "run_date": "no transcript and the report header carries no date.",
        "parent_turns": "no turn count recorded.",
    }
    A("| column | blank cells | of | why |\n|---|---|---|---|")
    for col in COLUMNS:
        blanks = sum(1 for r in rows if r[col] is None)
        if blanks:
            A(f"| {col} | {blanks} | {n} | {reasons.get(col, 'see column notes')} |")
    A("")
    A("Other limits, stated once:")
    A("- Child failure reasons are derived from gruntly's own statuses, not from reading the child's output. `tool-call error`, `unfinished` and `context overflow` cannot be told apart from `other` in the recorded data; the hosted-child runs (NVIDIA, Gemini free tier) mostly failed on connection/rate-limit errors that gruntly records as status `error`.")
    A("- The per-call `output` tokens in transcripts of some runs are streamed snapshots and sum to less than the reported output (`output_tokens_reconcile`); the run-level `parent_output` and the cost use the reported totals.")
    A("- Local children: LM Studio logs for 2026-11-07 to 2026-11-09 hold per-request token counts but, with several benchmarks and the user's own use sharing the server, no run identifier; they were not attributed to runs.")
    A("- Claude Code, OpenCode and Hermes versions: only the Claude Code version is recorded with the runs.")
    A("- Pass rates are small-sample: the arms are not a matched design across files (different task sets, repetitions and dates; the gruntly code changed between experiments).")
    if notes.get("row_tokens_incomplete"):
        A(f"- {len(notes['row_tokens_incomplete'])} rows with no transcript or persisted session ({', '.join(sorted({r.split('.')[0] for r in notes['row_tokens_incomplete']}))}) have result-row token totals that cover only part of the session (they price to a fraction of the reported cost: the parent backgrounded gruntly and the run continued in a second session). Their parent token columns and `cost_usd_computed` are left blank; `cost_usd_reported` is kept.")
    if notes.get("parent_model_from_report_header"):
        A(f"- parent_model for {len(notes['parent_model_from_report_header'])} rows without a transcript comes from the run report's header (the alias the run was started with); for {len(notes.get('parent_model_inferred_by_cost', []))} rows of the 'default model' runs it is inferred because only one model's price table reproduces the reported cost.")
    if notes.get("task_type"):
        A(f"- task_type is blank/unknown for: {', '.join(sorted(set(notes['task_type'])))}.")
    (out / "README.md").write_text("\n".join(L) + "\n", encoding="utf8")


if __name__ == "__main__":
    main_cli()
