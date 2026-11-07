"""Generates the larger bench tasks (the parent needs 8+ turns alone). Output is committed.

  bugs_batch   six independent small bugs, one failing test each (hidden tests add edge cases)
  rename_domain  rename a domain concept across 15 files (tests included)
  cli_json     add --json output to four commands of a small CLI, following the one that already has it

Each folder has repo/ (starter), hidden/test_hidden.py, reference/ (solved files, used only by validate_tasks.py),
and task.yaml.
"""
import re
import shutil
from pathlib import Path
from textwrap import dedent

import yaml

ROOT = Path(__file__).parent / "tasks"


def w(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(text).lstrip("\n"), encoding="utf8", newline="\n")


def fresh(name):
    d = ROOT / name
    shutil.rmtree(d, ignore_errors=True)
    return d


def write_yaml(d: Path, brief: str, acceptance: str, allowed=("**",), tests_writable=False):
    spec = {"brief": dedent(brief).strip(), "allowed_paths": list(allowed), "acceptance": [{"cmd": acceptance}]}
    if tests_writable:
        spec["tests_writable"] = True
    (d / "task.yaml").write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf8", newline="\n")


# ------------------------------------------------------------------ bugs_batch
BUGS = {
    "pager": ("paginate", '''
def paginate(items, page, per_page):
    start = page * per_page
    return items[start:start + per_page]
''', '''
def paginate(items, page, per_page):
    start = (page - 1) * per_page
    return items[start:start + per_page]
''', "from pager import paginate\n\ndef test_first_page():\n    assert paginate(list(range(10)), 1, 3) == [0, 1, 2]\n",
     "from pager import paginate\n\ndef test_edges():\n    assert paginate(list(range(10)), 4, 3) == [9]\n    assert paginate(list(range(10)), 5, 3) == []\n"),
    "words": ("word_count", '''
def word_count(text):
    counts = {}
    for w in text.split():
        counts[w] = counts.get(w, 0) + 1
    return counts
''', '''
import re

def word_count(text):
    counts = {}
    for w in re.findall(r"[a-z0-9']+", text.lower()):
        counts[w] = counts.get(w, 0) + 1
    return counts
''', "from words import word_count\n\ndef test_basic():\n    assert word_count('A b, a') == {'a': 2, 'b': 1}\n",
     "from words import word_count\n\ndef test_more():\n    assert word_count(\"It's fine; it's OK.\") == {\"it's\": 2, 'fine': 1, 'ok': 1}\n    assert word_count('') == {}\n"),
    "intervals": ("merge_intervals", '''
def merge_intervals(intervals):
    out = []
    for s, e in intervals:
        if out and s < out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out
''', '''
def merge_intervals(intervals):
    out = []
    for s, e in sorted([list(x) for x in intervals]):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out
''', "from intervals import merge_intervals\n\ndef test_basic():\n    assert merge_intervals([[2, 6], [1, 3]]) == [[1, 6]]\n",
     "from intervals import merge_intervals\n\ndef test_more():\n    assert merge_intervals([[1, 2], [2, 3]]) == [[1, 3]]\n    d = [[1, 4], [2, 5]]\n    merge_intervals(d)\n    assert d == [[1, 4], [2, 5]]\n    assert merge_intervals([]) == []\n"),
    "stats": ("median", '''
def median(values):
    v = sorted(values)
    return v[len(v) // 2]
''', '''
def median(values):
    if not values:
        raise ValueError("empty")
    v = sorted(values)
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2
''', "from stats import median\n\ndef test_even():\n    assert median([1, 2, 3, 4]) == 2.5\n",
     "import pytest\nfrom stats import median\n\ndef test_more():\n    assert median([3]) == 3\n    assert median([5, 1, 3]) == 3\n    with pytest.raises(ValueError):\n        median([])\n"),
    "limits": ("clamp", '''
def clamp(x, lo, hi):
    return max(hi, min(lo, x))
''', '''
def clamp(x, lo, hi):
    if lo > hi:
        raise ValueError("lo > hi")
    return max(lo, min(hi, x))
''', "from limits import clamp\n\ndef test_basic():\n    assert clamp(15, 0, 10) == 10\n    assert clamp(-5, 0, 10) == 0\n",
     "import pytest\nfrom limits import clamp\n\ndef test_more():\n    assert clamp(5, 0, 10) == 5\n    with pytest.raises(ValueError):\n        clamp(1, 10, 0)\n"),
    "chunks": ("chunk", '''
def chunk(items, n):
    return [items[i:i + n] for i in range(0, len(items) - n + 1, n)]
''', '''
def chunk(items, n):
    if n < 1:
        raise ValueError("n must be >= 1")
    return [items[i:i + n] for i in range(0, len(items), n)]
''', "from chunks import chunk\n\ndef test_remainder():\n    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]\n",
     "import pytest\nfrom chunks import chunk\n\ndef test_more():\n    assert chunk([], 3) == []\n    with pytest.raises(ValueError):\n        chunk([1], 0)\n"),
}


def make_bugs_batch():
    d = fresh("bugs_batch")
    hidden = []
    for mod, (fn, buggy, fixed, vis, hid) in BUGS.items():
        w(d / "repo" / f"{mod}.py", buggy)
        w(d / "repo" / f"test_{mod}.py", vis)
        w(d / "reference" / f"{mod}.py", fixed)
        hidden.append(hid)
    # one hidden file: merge the per-module hidden tests, de-duplicating imports
    imports = sorted({ln for h in hidden for ln in h.splitlines() if ln.startswith(("import ", "from "))})
    bodies = ["\n".join(ln for ln in h.splitlines() if not ln.startswith(("import ", "from "))) for h in hidden]
    names = {}
    out = []
    for b in bodies:  # rename test functions so they do not collide
        out.append(re.sub(r"def test_(\w+)", lambda m: f"def test_{m.group(1)}_{len(out)}", b))
    w(d / "hidden" / "test_hidden.py", "\n".join(imports) + "\n\n" + "\n".join(out) + "\n")
    write_yaml(d, """
        Six independent modules in this repo each have a bug that their visible test exposes: pager.py, words.py,
        intervals.py, stats.py, limits.py and chunks.py. Fix every one so the whole suite passes. Each fix should
        handle the obvious edge cases for that function (empty input, invalid arguments raise ValueError, inputs are
        not mutated), not just the visible test.
        """, "python -m pytest -q", allowed=[f"{m}.py" for m in BUGS])


# ------------------------------------------------------------------ rename_domain
def make_rename():
    d = fresh("rename_domain")
    w(d / "repo" / "models.py", '''
        from dataclasses import dataclass


        @dataclass
        class Customer:
            """A customer of the shop."""
            name: str
            tier: int = 1

            def customer_label(self) -> str:
                return f"Customer<{self.name}>"
    ''')
    w(d / "reference" / "models.py", '''
        from dataclasses import dataclass


        @dataclass
        class Account:
            """A account of the shop."""
            name: str
            tier: int = 1

            def account_label(self) -> str:
                return f"Account<{self.name}>"
    ''')
    for i in range(1, 14):
        src = f'''
            from models import Customer


            def customer_summary_{i}(customer: Customer) -> str:
                """Summary of a customer for report {i}."""
                return f"Customer {{customer.name}} (tier {{customer.tier + {i}}}) {{customer.customer_label()}}"
        '''
        w(d / "repo" / f"svc_{i}.py", src)
        w(d / "reference" / f"svc_{i}.py", src.replace("Customer", "Account").replace("customer", "account"))
        tsrc = f'''
            from models import Customer
            from svc_{i} import customer_summary_{i}


            def test_summary_{i}():
                c = Customer("Ann", 2)
                assert customer_summary_{i}(c) == "Customer Ann (tier {2 + i}) Customer<Ann>"
        '''
        w(d / "repo" / f"test_svc_{i}.py", tsrc)
        w(d / "reference" / f"test_svc_{i}.py", tsrc.replace("Customer", "Account").replace("customer", "account"))
    check = '''
        import pathlib
        import re
        import sys

        bad = []
        for p in pathlib.Path(".").glob("*.py"):
            if p.name == "check_names.py":
                continue
            for n, line in enumerate(p.read_text().splitlines(), 1):
                if re.search("customer", line, re.I):
                    bad.append(f"{p}:{n}: {line.strip()}")
        print("\\n".join(bad[:20]) or "no leftover names")
        sys.exit(1 if bad else 0)
    '''
    w(d / "repo" / "check_names.py", check)
    w(d / "reference" / "check_names.py", check)
    hidden = "from models import Account\n" + "".join(f"from svc_{i} import account_summary_{i}\n" for i in range(1, 14)) + '''

def test_all_renamed():
    a = Account("Zed", 3)
    assert a.account_label() == "Account<Zed>"
''' + "".join(f'''
def test_h{i}():
    assert account_summary_{i}(Account("Zed", 3)) == "Account Zed (tier {3 + i}) Account<Zed>"
''' for i in range(1, 14))
    w(d / "hidden" / "test_hidden.py", hidden)
    write_yaml(d, """
        Rename the domain concept "customer" to "account" everywhere in this repo: class Customer -> Account,
        every identifier, function name (customer_summary_N -> account_summary_N, customer_label ->
        account_label), variable, docstring, comment and output string, in the code AND in the tests (case-preserving:
        Customer -> Account, customer -> account). File names stay as they are. Done means no occurrence of
        'customer' (any case) remains in any .py file and the suite passes.
        """, "python check_names.py && python -m pytest -q", tests_writable=True)


# ------------------------------------------------------------------ cli_json
COMMANDS = {
    "status": {"state": "ok", "uptime": 42},
    "list": {"items": ["a", "b", "c"]},
    "show": {"id": 7, "title": "demo", "tags": ["x", "y"]},
    "stats": {"count": 12, "mean": 3.5},
    "users": {"users": [{"name": "ann", "role": "admin"}, {"name": "bo", "role": "dev"}]},
    "jobs": {"queued": 2, "running": 1},
    "logs": {"lines": ["start", "work", "done"]},
    "config": {"debug": False, "retries": 3},
}


def text_for(cmd, data):
    if isinstance(data, dict):
        return "\\n".join(f"{k}: {v}" for k, v in data.items())
    return str(data)


def make_cli_json():
    d = fresh("cli_json")
    mod = d / "repo" / "tool"
    w(mod / "__init__.py", "")
    for cmd, data in COMMANDS.items():
        w(mod / f"cmd_{cmd}.py", f'''
            """The `{cmd}` command."""

            def collect():
                return {data!r}


            def render(data):
                return "\\n".join(f"{{k}}: {{v}}" for k, v in data.items())
        ''')
    w(mod / "cli.py", '''
        """Dispatcher. Commands that support --json are listed in JSON_COMMANDS and share the same code path."""
        import importlib
        import json
        import sys

        JSON_COMMANDS = {"status"}


        def run(argv):
            if not argv:
                raise SystemExit("usage: tool <command> [--json]")
            cmd, flags = argv[0], argv[1:]
            mod = importlib.import_module(f"tool.cmd_{cmd}")
            data = mod.collect()
            if "--json" in flags:
                if cmd not in JSON_COMMANDS:
                    raise SystemExit(f"--json is not supported for {cmd}")
                return json.dumps(data, sort_keys=True)
            return mod.render(data)


        if __name__ == "__main__":
            print(run(sys.argv[1:]))
    ''')
    w(d / "repo" / "test_status.py", '''
        import json

        from tool.cli import run


        def test_status_text():
            assert run(["status"]) == "state: ok\\nuptime: 42"


        def test_status_json():
            assert json.loads(run(["status", "--json"])) == {"state": "ok", "uptime": 42}
    ''')
    w(d / "repo" / "test_json_new.py", '''
        import json

        import pytest

        from tool.cli import run


        @pytest.mark.parametrize("cmd", ["list", "show", "stats", "users"])
        def test_json_supported(cmd):
            assert isinstance(json.loads(run([cmd, "--json"])), dict)
    ''')
    w(d / "reference" / "tool" / "cli.py", (d / "repo" / "tool" / "cli.py").read_text(encoding="utf8").replace(
        'JSON_COMMANDS = {"status"}', 'JSON_COMMANDS = {"status", "list", "show", "stats", "users"}'))
    exp = {c: COMMANDS[c] for c in ("list", "show", "stats", "users")}
    w(d / "hidden" / "test_hidden.py", f'''
        import json

        import pytest

        from tool.cli import run

        EXPECTED = {exp!r}


        @pytest.mark.parametrize("cmd", sorted(EXPECTED))
        def test_json_matches(cmd):
            assert json.loads(run([cmd, "--json"])) == EXPECTED[cmd]


        @pytest.mark.parametrize("cmd", ["jobs", "logs", "config"])
        def test_other_commands_still_refuse_json(cmd):
            with pytest.raises(SystemExit):
                run([cmd, "--json"])


        @pytest.mark.parametrize("cmd", sorted(EXPECTED))
        def test_text_output_unchanged(cmd):
            assert "--json" not in run([cmd])
            assert run([cmd]).splitlines()
    ''')
    write_yaml(d, """
        The `tool` CLI (tool/cli.py) supports `--json` only for the `status` command. Add `--json` support for the
        `list`, `show`, `stats` and `users` commands, following exactly how `status` does it. The other commands
        (jobs, logs, config) must keep refusing --json, and text output must not change.
        """, "python -m pytest -q", allowed=["tool/**"])


if __name__ == "__main__":
    make_bugs_batch()
    make_rename()
    make_cli_json()
    print("wrote large tasks")
