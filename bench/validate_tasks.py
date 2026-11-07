"""Sanity check for the task set: the starter fails its visible test, a reference solution passes visible + hidden."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent

REF = {
"slugify": 'import re\ndef slugify(t):\n    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")\n',
"pager": 'def paginate(items, page, per_page):\n    s = (page - 1) * per_page\n    return items[s:s + per_page]\n',
"durations": r'''import re
def parse_duration(s):
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", s)
    if not s or not m:
        raise ValueError(s)
    h, mi, se = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + se
''',
"lru": '''from collections import OrderedDict
class LRUCache:
    def __init__(self, capacity):
        self.c, self.d = capacity, OrderedDict()
    def get(self, k):
        if k not in self.d:
            return None
        self.d.move_to_end(k)
        return self.d[k]
    def put(self, k, v):
        self.d[k] = v
        self.d.move_to_end(k)
        if len(self.d) > self.c:
            self.d.popitem(last=False)
''',
"words": 'import re\ndef word_count(t):\n    out = {}\n    for w in re.findall(r"[a-z0-9\']+", t.lower()):\n        out[w] = out.get(w, 0) + 1\n    return out\n',
"flat": 'def flatten(x):\n    out = []\n    for i in x:\n        out.extend(flatten(i) if isinstance(i, list) else [i])\n    return out\n',
"retrying": '''import functools
def retry(times, exceptions=(Exception,)):
    def deco(f):
        @functools.wraps(f)
        def w(*a, **k):
            for i in range(times):
                try:
                    return f(*a, **k)
                except exceptions:
                    if i == times - 1:
                        raise
        return w
    return deco
''',
"roman": '''import re
V = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
def to_roman(n):
    if not 1 <= n <= 3999:
        raise ValueError(n)
    out = ""
    for v, s in V:
        while n >= v:
            out += s; n -= v
    return out
def from_roman(s):
    if not s or not re.fullmatch(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", s):
        raise ValueError(s)
    n, i = 0, 0
    for v, r in V:
        while s.startswith(r, i):
            n += v; i += len(r)
    return n
''',
"intervals": 'def merge_intervals(iv):\n    out = []\n    for s, e in sorted([list(x) for x in iv]):\n        if out and s <= out[-1][1]:\n            out[-1][1] = max(out[-1][1], e)\n        else:\n            out.append([s, e])\n    return out\n',
"rolling": 'def rolling_mean(v, w):\n    if w < 1:\n        raise ValueError(w)\n    return [sum(v[i:i + w]) / w for i in range(len(v) - w + 1)]\n',
}


def pytest(cwd, *args):
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args], cwd=cwd,
                          capture_output=True, text=True).returncode


def main() -> int:
    bad = 0
    for t in sorted((HERE / "tasks").iterdir()):
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp) / "r"
            shutil.copytree(t / "repo", w)
            mod = next(p for p in w.glob("*.py") if not p.name.startswith("test_"))
            starter_fails = pytest(w, "-x") != 0
            mod.write_text(REF[mod.stem], encoding="utf8")
            shutil.copy(t / "hidden" / "test_hidden.py", w / "test_hidden.py")
            ref_passes = pytest(w) == 0
            ok = starter_fails and ref_passes
            bad += not ok
            print(f"{'ok ' if ok else 'BAD'} {t.name}: starter_fails={starter_fails} reference_passes={ref_passes}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
