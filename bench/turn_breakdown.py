"""What was each parent turn? One line per turn from the stored stream-json transcripts, plus a tally by kind and the dollars of each.

  python bench/turn_breakdown.py DIR [TASK ...]

DIR is a folder under bench/ (for example runs-real-claude). It prints the turns of the named tasks, then a tally over every run in DIR.
Dollars per turn are estimated from the cache read and write counts in the transcript at Sonnet 5.5 prices; the stream under-reports
output tokens, so a run's total here is 15-30% under the figure the session was billed.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
PRICE = dict(read=0.10e-6, write=4e-6, out=10e-6)   # Sonnet 5.5, $ per token


def short(s, n=70):
    return " ".join(str(s).split())[:n]


def kind_of(block):
    n, i = block.get("name"), block.get("input") or {}
    cmd = str(i.get("command", ""))
    if n == "Bash" and "gruntly" in cmd:
        if "--continue" in cmd:
            return "send the child a follow-up (--continue)"
        m = re.search(r"gruntly\s+(agent-run|wait|discard|diff|apply)", cmd)
        return {"agent-run": "delegate: gruntly agent-run", "wait": "wait for the child (gruntly wait)", "discard": "discard the child's work",
                "diff": "read the child's diff", "apply": "apply the child's patch"}.get(m.group(1) if m else "", "other gruntly call")
    if n == "Bash":
        return "run tests / shell by the parent" if re.search(r"pytest|python|git ", cmd) else "other shell"
    if n in ("Read", "Grep", "Glob"):
        return "read / search the code by the parent"
    if n in ("Edit", "Write", "MultiEdit"):
        return "edit by the parent (takeover)"
    if n == "Skill":
        return "load a skill"
    return f"other tool ({n})"


def turns(path):
    seen, out = {}, []
    for line in path.open(encoding="utf8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "assistant":
            continue
        m = e.get("message", {})
        mid = m.get("id") or id(m)
        t = seen.get(mid)
        if t is None:
            u = m.get("usage") or {}
            t = {"read": u.get("cache_read_input_tokens") or 0, "write": u.get("cache_creation_input_tokens") or 0, "out": u.get("output_tokens") or 0,
                 "blocks": []}
            seen[mid] = t
            out.append(t)
        for b in m.get("content", []):
            if b.get("type") == "tool_use":
                inp = b.get("input") or {}
                t["blocks"].append(kind_of(b) + "|" + short(inp.get("command") or inp.get("file_path") or inp.get("pattern") or ""))
            elif b.get("type") == "text" and b.get("text", "").strip():
                t["blocks"].append("final reply / message|" + short(b["text"]))
    for t in out:
        t["usd"] = t["read"] * PRICE["read"] + t["write"] * PRICE["write"] + t["out"] * PRICE["out"]
    return out


def main():
    d = ROOT / sys.argv[1]
    want = set(sys.argv[2:])
    tally, usd = Counter(), defaultdict(float)
    nruns = nturns = 0
    for p in sorted(d.glob("*.jsonl")):
        ts = turns(p)
        nruns += 1
        nturns += len(ts)
        for i, t in enumerate(ts):
            k = (t["blocks"][0].split("|")[0] if t["blocks"] else "thinking only")
            if i == 0 and "delegate" in k:
                k = "delegate: gruntly agent-run (FIRST turn)"
            tally[k] += 1
            usd[k] += t["usd"]
        if p.name.split(".")[0] in want:
            print(f"\n--- {p.name}: {len(ts)} turns, ${sum(t['usd'] for t in ts):.3f}")
            for i, t in enumerate(ts, 1):
                print(f"  turn {i}: ctx {t['read'] + t['write']:>6,} tok (cache write {t['write']:>6,}), out {t['out']:>4}, ${t['usd']:.4f} | "
                      + " ; ".join(t["blocks"])[:170])
    print(f"\nTALLY over {nruns} runs, {nturns} turns")
    for k, v in tally.most_common():
        print(f"  {v:3d} turns  ${usd[k]:.3f}  {k}")


if __name__ == "__main__":
    main()
