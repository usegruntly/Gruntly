"""Builds one verbatim, chronological log of a delegated task from two sources:

  1. Claude Code's stream-json transcript (what the parent said, called and received)
  2. gruntly's run directory in the repo (.gruntly/runs/<id>/): the spec, the exact prompt and command sent to the
     child, the child's raw output, each gate's output, the diff and the result returned to the parent

  claude -p --output-format stream-json --verbose ... > transcript.jsonl
  python bench/trace.py --transcript transcript.jsonl --repo <repo> --out logs/trace.log

Nothing is truncated or summarised. Claude's own system prompt is not part of stream-json, so it is not included.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

RULE = "=" * 100
SUB = "-" * 100


def block(title: str, body: str) -> str:
    return f"\n{SUB}\n{title}\n{SUB}\n{body.rstrip()}\n"


def pretty(obj) -> str:
    """JSON with string values un-escaped so multi-line commands and file contents read as written."""
    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            if isinstance(v, str) and ("\n" in v or len(v) > 100):
                parts.append(f"{k}:\n" + "\n".join("    " + ln for ln in v.splitlines()))
            else:
                parts.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        return "\n".join(parts)
    return json.dumps(obj, indent=2, ensure_ascii=False)


def content_text(c) -> str:
    if isinstance(c, str):
        return c
    out = []
    for b in c or []:
        if isinstance(b, dict) and b.get("type") == "text":
            out.append(b.get("text", ""))
        else:
            out.append(json.dumps(b, ensure_ascii=False))
    return "\n".join(out)


# ----------------------------------------------------------------- the child's raw output
def render_child_event(e: dict) -> str:
    t = e.get("type")
    part = e.get("part") or {}
    if t == "step_start":
        return "[step start]"
    if t == "text":
        return "[model text]\n" + part.get("text", "")
    if t == "tool_use":  # OpenCode
        st = part.get("state") or {}
        return (f"[model calls tool: {part.get('tool')}  status={st.get('status')}]\n"
                f"input:\n{pretty(st.get('input', {}))}\noutput:\n{st.get('output', '')}")
    if t == "step_finish":
        tk = part.get("tokens") or {}
        return f"[step finish reason={part.get('reason')}  tokens in={tk.get('input')} out={tk.get('output')} total={tk.get('total')}]"
    if t == "assistant":  # Qwen Code
        out = []
        for b in e.get("message", {}).get("content", []):
            if b.get("type") == "tool_use":
                out.append(f"[model calls tool: {b.get('name')}]\n{pretty(b.get('input', {}))}")
            elif b.get("type") == "text":
                out.append("[model text]\n" + b.get("text", ""))
            elif b.get("type") == "thinking":
                out.append("[model thinking]\n" + b.get("thinking", ""))
        return "\n".join(out)
    if t == "user":
        return "[tool result]\n" + "\n".join(content_text(b.get("content")) for b in e.get("message", {}).get("content", [])
                                              if isinstance(b, dict))
    if t == "result":
        return f"[final result]\n{e.get('result', '')}\nusage: {json.dumps(e.get('usage'))}"
    return json.dumps(e, ensure_ascii=False)


def render_child_log(text: str) -> str:
    out = []
    for m in re.split(r"(?m)^(?==== attempt \d+ )", text):
        if not m.strip():
            continue
        header, _, rest = m.partition("\n")
        stdout, _, stderr = rest.partition("--- stderr ---")
        out.append(f"\n##### {header.strip(' =')} #####")
        rendered = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                rendered.append(render_child_event(json.loads(line)))
            except json.JSONDecodeError:
                rendered.append(line)
        out.append("\n\n".join(rendered) if rendered else "(no stdout)")
        if stderr.strip():
            out.append("\n[child stderr]\n" + stderr.strip())
    return "\n".join(out)


# ----------------------------------------------------------------- gruntly's side of one run
def gruntly_section(repo: Path, run_id: str) -> str:
    d = repo / ".gruntly" / "runs" / run_id
    if not d.is_dir():
        return f"(no run directory for {run_id})"
    rd = lambda n: (d / n).read_text(encoding="utf8", errors="replace") if (d / n).exists() else ""  # noqa: E731
    out = [f"\n{RULE}\nINSIDE GRUNTLY: run {run_id}   ({d})\n{RULE}"]
    out.append(block("1. SPEC gruntly was given (spec.json, after merging defaults, .gruntly.toml and the spec)", rd("spec.json")))
    for a in sorted((d / "attempts").glob("*"), key=lambda p: int(p.name)) if (d / "attempts").exists() else []:
        n = a.name
        out.append(block(f"2.{n}  COMMAND gruntly ran for the local model, attempt {n} (command.json)", rd(f"attempts/{n}/command.json")))
        out.append(block(f"3.{n}  EXACT PROMPT sent to the local model, attempt {n}", rd(f"attempts/{n}/prompt.txt")))
    out.append(block("4. WHAT THE LOCAL MODEL DID (raw child output, rendered event by event, nothing cut)",
                     render_child_log(rd("child.log"))))
    for a in sorted((d / "attempts").glob("*"), key=lambda p: int(p.name)) if (d / "attempts").exists() else []:
        n = a.name
        gates = "\n".join(f"--- gate: {g.stem.removeprefix('gate_')} ---\n{g.read_text(encoding='utf8', errors='replace') or '(passed, no output)'}"
                          for g in sorted(a.glob("gate_*.txt")))
        out.append(block(f"5.{n}  GATES gruntly ran itself after attempt {n} (failure output; empty means it passed)", gates))
        out.append(block(f"6.{n}  DIFF the child produced, attempt {n}", rd(f"attempts/{n}/diff.patch") or "(empty)"))
    out.append(block("7. WHAT GRUNTLY SENT BACK TO CLAUDE (result.json, the only thing the parent reads)", rd("result.json")))
    out.append(block("8. run state (status.json)", rd("status.json")))
    out.append(f"{RULE}\nEND INSIDE GRUNTLY\n{RULE}\n")
    return "\n".join(out)


# ----------------------------------------------------------------- Claude's side
def build(transcript: Path, repo: Path) -> str:
    out = [f"{RULE}\nTRACE OF ONE DELEGATED TASK\n{RULE}",
           "Reading guide: 'CLAUDE' = the paid parent agent. 'INSIDE GRUNTLY' = what gruntly did with the local model.\n"
           "Everything is verbatim and in time order. Claude's own system prompt is not in the transcript format.\n"]
    seen: set[str] = set()
    pending: dict[str, str] = {}
    step = 0
    for line in transcript.read_text(encoding="utf8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = e.get("type")
        if t == "system" and e.get("subtype") == "init":
            out.append(block("SESSION START", pretty({k: e.get(k) for k in ("model", "cwd", "permissionMode", "tools", "mcp_servers",
                                                                           "plugins", "skills", "slash_commands") if k in e})))
        elif t == "assistant":
            for b in e.get("message", {}).get("content", []):
                if b.get("type") == "text" and b.get("text", "").strip():
                    step += 1
                    out.append(block(f"[{step}] CLAUDE SAYS", b["text"]))
                elif b.get("type") == "thinking" and b.get("thinking", "").strip():
                    out.append(block("CLAUDE THINKING", b["thinking"]))
                elif b.get("type") == "tool_use":
                    step += 1
                    pending[b["id"]] = b.get("name", "?")
                    out.append(block(f"[{step}] CLAUDE CALLS TOOL: {b.get('name')}", pretty(b.get("input", {}))))
        elif t == "user":
            msg = e.get("message", {})
            c = msg.get("content")
            if isinstance(c, str):
                out.append(block("INPUT TO CLAUDE", c))
                continue
            for b in c or []:
                if b.get("type") == "tool_result":
                    txt = content_text(b.get("content"))
                    out.append(block(f"TOOL RESULT returned to Claude (from {pending.get(b.get('tool_use_id'), '?')})", txt))
                    for rid in re.findall(r"r_\d{8}_[0-9a-f]{4}", txt):
                        if rid not in seen:
                            seen.add(rid)
                            out.append(gruntly_section(repo, rid))
                elif b.get("type") == "text":
                    out.append(block("INPUT TO CLAUDE", b.get("text", "")))
        elif t == "result":
            u = e.get("usage") or {}
            out.append(block("SESSION END", pretty({"result": e.get("result"), "num_turns": e.get("num_turns"),
                                                    "total_cost_usd": e.get("total_cost_usd"), "duration_ms": e.get("duration_ms"),
                                                    "usage": {k: u.get(k) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                                                                    "cache_read_input_tokens")}})))
    for rid in sorted(p.name for p in (repo / ".gruntly" / "runs").glob("r_*")) if (repo / ".gruntly" / "runs").exists() else []:
        if rid not in seen:  # a run Claude never printed an id for (e.g. async started in the background)
            out.append(gruntly_section(repo, rid))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(build(Path(a.transcript), Path(a.repo)), encoding="utf8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
