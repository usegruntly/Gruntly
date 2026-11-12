"""Stand-in for `claude -p` as a gruntly child. usage: fake_claude.py <scenario> [claude flags...]; the prompt arrives on stdin.
It records how it was called in <git dir>/fake_claude_call.json (inside the git directory, so it is not part of the diff) and
prints the same stream-json events Claude Code prints."""
import json
import subprocess
import sys
from pathlib import Path

scenario = sys.argv[1]
flags = sys.argv[2:]
if "--version" in flags:                          # the adapter's installed-check: answer and touch nothing
    print("2.1.322 (Claude Code, stand-in)")
    sys.exit(0)
prompt = sys.stdin.read()
gitdir = Path(subprocess.run(["git", "rev-parse", "--absolute-git-dir"], capture_output=True, text=True).stdout.strip())
calls = gitdir / "fake_claude_call.json"
seen = json.loads(calls.read_text()) if calls.exists() else []
calls.write_text(json.dumps(seen + [{"flags": flags, "prompt": prompt}]))


def result(text, cost, **over):
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 5, "result": text,
                       "session_id": "sess-1", "total_cost_usd": cost,
                       "usage": {"input_tokens": 30, "cache_read_input_tokens": 8000, "cache_creation_input_tokens": 500,
                                 "output_tokens": 400}, **over})


print(json.dumps({"type": "system", "subtype": "init"}))
if scenario == "pass":
    Path("calc.py").write_text("def add(a, b):\n    return a + b\n")
    print(result("fixed add()", 0.0100))
elif scenario == "fix_on_retry":
    if "--resume" in flags:
        Path("calc.py").write_text("def add(a, b):\n    return a + b\n")
        print(result("fixed on retry", 0.0070))
    else:
        print(result("looked around, changed nothing", 0.0050))
elif scenario == "out_of_budget":
    print(result("", 0.5000, subtype="error_max_budget_usd"))
    sys.exit(1)
