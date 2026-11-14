"""A compact, tool-independent account of what a child agent DID, built from the structured events it already prints.

OpenCode (`run --format json`), Qwen Code (`-o json|stream-json`) and Hermes (`--format stream-json`) each print tool calls in
their own shape. This turns them into one list of calls and a short summary the parent can read in about 50 tokens:

    child: 6 tool calls (read x2, edit x1, run x3), 0 failed, 1 test run

Nothing the child wrote is copied into the summary (only counts and tool-kind names), so it is safe to show unfenced. The
diff itself is not taken from here: events are agent-reported, and the worktree's `git diff` stays the ground truth.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass

READ = {"read", "read_file", "readfile", "glob", "grep", "list", "ls", "search", "search_file_content", "list_directory",
        "find", "codesearch", "webfetch"}
EDIT = {"edit", "write", "write_file", "writefile", "rewrite_file", "replace", "patch", "apply_patch", "multiedit",
        "create_file", "str_replace_editor"}
RUN = {"bash", "shell", "run_shell_command", "execute", "run_command", "terminal"}
TEST_WORDS = ("pytest", "unittest", "npm test", "go test", "cargo test", "tox", "nose")
REPEAT_FLAG = 3        # the same call this many times = the child is going round in circles
FAIL_FLAG = 0.5        # at least half of the calls failing


@dataclass
class Call:
    tool: str
    kind: str          # read | edit | run | other
    ok: bool
    sig: str           # stable fingerprint of (tool, input), used only to count repeats
    is_test: bool = False
    what: str = ""      # short human label: a path or the start of a command


def kind_of(tool: str) -> str:
    t = (tool or "").lower()
    return "read" if t in READ else "edit" if t in EDIT else "run" if t in RUN else "other"


def _shell_failed(state: dict) -> bool:
    """A shell command that ran but failed (non-zero exit, or a Python traceback) is not a success."""
    meta = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    code = meta.get("exit")
    if isinstance(code, int) and code != 0:
        return True
    return "Traceback (most recent call last)" in str(state.get("output") or meta.get("output") or "")[:20000]


def _what(kind: str, args, cmd: str) -> str:
    """A short label for a tool call; never file contents."""
    if not isinstance(args, dict):
        return ""
    if kind == "run":
        return " ".join(cmd.split())[:90]
    for k in ("filePath", "file_path", "path", "pattern", "url", "query", "absolute_path"):
        if args.get(k):
            v = str(args[k]).replace("\\", "/")
            return "/".join(v.split("/")[-3:])[:90]
    return ""


def _call(tool: str, args, ok: bool) -> Call:
    try:
        # The WHOLE input counts. Cut at 400 characters, two different scripts that open with the same unpacking boilerplate looked identical,
        # and a child extracting facts from a bundled page was stopped as "going round in circles" after six of them (real run, 2026-11-14).
        sig = tool + hashlib.sha1(json.dumps(args, sort_keys=True, default=str).encode("utf8", "replace")).hexdigest()
    except (TypeError, ValueError):
        sig = tool
    kind = kind_of(tool)
    cmd = ""
    if kind == "run" and isinstance(args, dict):
        cmd = str(args.get("command") or args.get("cmd") or "")
    return Call(tool, kind, ok, sig, kind == "run" and any(w in cmd for w in TEST_WORDS), _what(kind, args, cmd))


def _events(stdout: str) -> list:
    s = (stdout or "").strip()
    if not s:
        return []
    try:
        data = json.loads(s)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        pass
    out = []
    for line in s.splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def calls_from(stdout: str) -> list[Call]:
    """Accepts any of the three shapes; unknown lines are ignored, so a changed format degrades to an empty trace."""
    calls: list[Call] = []
    pending: dict[str, int] = {}                     # Qwen/Hermes: tool_use first, tool_result later
    for e in _events(stdout):
        if not isinstance(e, dict):
            continue
        part = e.get("part")
        if e.get("type") == "tool_use" and isinstance(part, dict) and part.get("type") == "tool":      # OpenCode
            state = part.get("state") or {}
            ok = state.get("status") != "error" and not _shell_failed(state)
            calls.append(_call(str(part.get("tool", "")), state.get("input"), ok))
            continue
        msg = e.get("message")
        blocks = msg.get("content") if isinstance(msg, dict) else None
        for b in blocks if isinstance(blocks, list) else []:                                           # Qwen
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                calls.append(_call(str(b.get("name", "")), b.get("input"), True))
                pending[str(b.get("id"))] = len(calls) - 1
            elif b.get("type") == "tool_result" and str(b.get("tool_use_id")) in pending and b.get("is_error"):
                calls[pending[str(b["tool_use_id"])]].ok = False
        if e.get("type") == "tool_use" and "name" in e and not isinstance(part, dict):                   # Hermes
            calls.append(_call(str(e["name"]), e.get("input"), True))
        elif e.get("type") == "tool_result" and "name" in e and e.get("is_error") and calls:
            calls[-1].ok = False
    return calls


CLAIM = re.compile(r"(?i)\b(done|complete[d]?|implemented|fixed|added|updated|changed|finished|resolved)\b")
NO_CLAIM = re.compile(r"(?i)\b(already|no changes?|nothing to (?:do|change|fix))\b")


def narrated_work(calls: list[Call], message: str, files_changed: int) -> bool:
    """The child's trace shows tool calls but no edit, nothing changed on disk, and its final message says the work is done:
    it described the change instead of making it. (`already done` and `no change needed` are not claims.) With no trace
    (Hermes in quiet mode) this is never true: the empty diff and the failing check say the same thing a turn later."""
    return (bool(calls) and files_changed == 0 and not any(c.kind == "edit" for c in calls)
            and bool(CLAIM.search(message or "")) and not NO_CLAIM.search(message or ""))


def summarize(calls: list[Call]) -> dict:
    if not calls:
        return {}
    kinds = Counter(c.kind for c in calls)
    sigs = Counter(c.sig for c in calls)
    return {"calls": len(calls), "kinds": dict(kinds), "failed": sum(not c.ok for c in calls),
            "test_runs": sum(c.is_test for c in calls), "max_repeat": max(sigs.values())}


def merge(a: dict, b: dict) -> dict:
    """Totals across attempts (repeat count is the worst single attempt)."""
    if not a:
        return dict(b)
    if not b:
        return dict(a)
    kinds = Counter(a.get("kinds", {})) + Counter(b.get("kinds", {}))
    return {"calls": a["calls"] + b["calls"], "kinds": dict(kinds), "failed": a["failed"] + b["failed"],
            "test_runs": a["test_runs"] + b["test_runs"], "max_repeat": max(a["max_repeat"], b["max_repeat"])}


def line(t: dict) -> str:
    """One short line, counts only."""
    if not t:
        return ""
    order = [k for k in ("read", "edit", "run", "other") if t["kinds"].get(k)]
    kinds = ", ".join(f"{k} x{t['kinds'][k]}" for k in order)
    out = f"child: {t['calls']} tool calls ({kinds}), {t['failed']} failed, {t['test_runs']} test run" + ("" if t["test_runs"] == 1 else "s")
    if t.get("max_repeat", 1) >= REPEAT_FLAG:
        out += f", one call repeated {t['max_repeat']} times"
    return out


def concerns(t: dict) -> list[str]:
    """Reasons for the parent to look closer, from behaviour alone."""
    if not t:
        return []
    out = []
    if t.get("max_repeat", 1) >= REPEAT_FLAG:
        out.append(f"the child repeated one tool call {t['max_repeat']} times")
    if t["calls"] >= 4 and t["failed"] / t["calls"] >= FAIL_FLAG:
        out.append(f"{t['failed']} of {t['calls']} child tool calls failed")
    if t.get("kinds", {}).get("edit") and not t.get("test_runs"):
        out.append("the child edited files but ran no test itself (only gruntly's own check ran)")
    return out
