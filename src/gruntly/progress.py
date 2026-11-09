"""A live, compact feed of what is happening inside a run: `.gruntly/runs/<id>/progress.jsonl`, one JSON object per line.

Three actors (field `who`):
  child    the local/small model: the tool calls it makes and one line of what it says
  gruntly  gruntly itself: starting an attempt, running the checks, a retry, a wait for a rate limit
  (the parent, Claude, is not here: its own steps are already in the Claude Code chat)

The feed is for people, not for the parent's context: `gruntly watch` and the Claude Code panel read it, and the result block
the parent receives is unchanged. It holds short labels (a tool name, a path or the start of a command, one line of the
child's own words) and `diff` rows: a capped copy of the child's changes so far, for the diff view. All of it passes through
redaction and none of it reaches the parent's context.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .redact import redact
from .trace import calls_from

NAME = "progress.jsonl"
SAY_CHARS = 160


class Feed:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, who: str, k: str, **fields) -> None:
        row = {"t": round(time.time(), 2), "who": who, "k": k, **{a: b for a, b in fields.items() if b not in (None, "")}}
        try:
            with self.path.open("a", encoding="utf8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass


def events_from_line(line: str) -> list[dict]:
    """The child events one line of its structured output contains (OpenCode, Qwen Code or Hermes shapes)."""
    line = line.strip()
    if not line.startswith("{"):
        return []
    out: list[dict] = []
    for c in calls_from(line):
        out.append({"k": "tool", "tool": c.tool, "kind": c.kind, "what": c.what, "ok": c.ok})
    try:
        e = json.loads(line)
    except ValueError:
        return out
    if not isinstance(e, dict):
        return out
    part = e.get("part") if isinstance(e.get("part"), dict) else {}
    if e.get("type") == "text" and part.get("text"):                  # OpenCode: the model's own words
        out.append({"k": "say", "text": " ".join(str(part["text"]).split())[:SAY_CHARS]})
    elif e.get("type") == "step_finish":
        t = part.get("tokens") or {}
        out.append({"k": "step", "tokens_in": t.get("input"), "tokens_out": t.get("output")})
    return out


DIFF_LINES = 40
DIFF_WIDTH = 140
HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")


def compact_diff(patch: str, limit: int = DIFF_LINES) -> dict:
    """A unified diff squeezed for the live view, capped at `limit` changed/context lines in all.

    Returns {"files": n, "ins": n, "del": n, "more": lines left out, "parts": [{"path", "tag", "text"}]}.
    Each part's text is valid unified-diff hunks (a hunk cut by the cap gets its header counts rewritten), so Claude Code's own
    diff highlighter can draw it."""
    files, ins, dele, total = 0, 0, 0, 0
    parts: list[dict] = []
    cur = None          # the file being read: {"path", "hunks": [[header, start_old, start_new, tail, body]]}
    for ln in patch.splitlines():
        if ln.startswith("diff --git"):
            files += 1
            cur = {"path": ln.split(" b/", 1)[-1], "tag": "", "hunks": []}
            parts.append(cur)
        elif cur is None:
            continue
        elif ln.startswith("new file"):
            cur["tag"] = " (new)"
        elif ln.startswith("deleted file"):
            cur["tag"] = " (deleted)"
        elif ln.startswith("Binary files"):
            cur["tag"] = " (binary)"
        elif ln.startswith(("index ", "--- ", "+++ ", "similarity", "old mode", "new mode", "\\ No newline")):
            continue
        else:
            m = HUNK.match(ln)
            if m:
                cur["hunks"].append([int(m.group(1)), int(m.group(2)), m.group(3), []])
            elif cur["hunks"] and ln[:1] in ("+", "-", " ", ""):
                cur["hunks"][-1][3].append(ln if ln else " ")
                total += 1
                ins += ln.startswith("+")
                dele += ln.startswith("-")
    budget, out = limit, []
    for f in parts:
        texts = []
        for old_start, new_start, tail, body in f["hunks"]:
            if budget <= 0:
                break
            kept = body[:budget]
            budget -= len(kept)
            kept = [redact(k[:DIFF_WIDTH], []) for k in kept]
            old_n = sum(1 for k in kept if k[0] in " -")
            new_n = sum(1 for k in kept if k[0] in " +")
            texts.append(f"@@ -{old_start},{old_n} +{new_start},{new_n} @@{tail}\n" + "\n".join(kept))
        out.append({"path": f["path"], "tag": f["tag"], "text": "\n".join(texts)})
    return {"parts": [t for t in out if t["text"]], "files": files, "ins": ins, "del": dele,
            "more": max(0, total - limit) if total > limit else 0}


def clean(row: dict) -> dict:
    """Redaction for the free-text fields."""
    for f in ("what", "text"):
        if isinstance(row.get(f), str):
            row[f] = redact(row[f], [])
    return row


def read_from(path: Path, offset: int = 0) -> tuple[list[dict], int]:
    """New rows since `offset` bytes, and the new offset. A partial last line is left for the next read."""
    try:
        with path.open("rb") as f:
            f.seek(offset)
            data = f.read()
    except OSError:
        return [], offset
    end = data.rfind(b"\n") + 1
    rows = []
    for ln in data[:end].decode("utf8", "replace").splitlines():
        try:
            rows.append(json.loads(ln))
        except ValueError:
            continue
    return rows, offset + end


def format_diff(r: dict, color: bool = False) -> list[str]:
    """A diff row as terminal lines: green additions, red removals."""
    head = f"  changes (attempt {r.get('n')}): {r.get('files', 0)} file(s), +{r.get('ins', 0)} -{r.get('dele', 0)}"
    out = [head]
    flat = [x for t in r.get("parts", []) for x in ["F " + t["path"] + t["tag"], *t["text"].splitlines()]]
    for ln in flat:
        c = ""
        if color:
            c = "\x1b[32m" if ln.startswith("+") else "\x1b[31m" if ln.startswith("-") else "\x1b[1m" if ln.startswith("F ") else "\x1b[2m"
        out.append(f"    {c}{ln}{chr(27) + '[0m' if color else ''}")
    if r.get("more"):
        out.append(f"    ... {r['more']} more lines (gruntly diff RUN shows all)")
    return out


KIND_VERB ={"read": "read", "edit": "edit", "run": "run", "other": "tool"}


def format_row(r: dict) -> str:
    """One plain-text line for `gruntly watch` (colour is added by the caller)."""
    who, k = r.get("who", "?"), r.get("k")
    stamp = time.strftime("%H:%M:%S", time.localtime(r.get("t", 0)))
    if k == "tool":
        body = f"{KIND_VERB.get(r.get('kind'), 'tool'):<5} {r.get('what', '') or r.get('tool', '')}" + ("" if r.get("ok", True) else "  (failed)")
    elif k == "say":
        body = f"says: {r.get('text', '')}"
    elif k == "step":
        body = f"model call done ({r.get('tokens_in') or '?'} in, {r.get('tokens_out') or '?'} out)"
    elif k == "start":
        body = f"run started: {r.get('model', '?')} via {r.get('harness', '?')}" + (f" on {r['provider']}" if r.get("provider") else "")
    elif k == "attempt":
        body = f"attempt {r.get('n')} started"
    elif k == "gates":
        body = "checks: " + (r.get("detail") or ("all passed" if r.get("ok") else "failed"))
    elif k == "wait":
        body = f"waiting {r.get('secs')}s ({r.get('why', 'rate limit')})"
    elif k == "done":
        body = f"finished: {r.get('status')}" + (f" ({r['reason']})" if r.get("reason") else "")
    else:
        body = k or "?"
    return f"{stamp}  {who:<7} {body}"
