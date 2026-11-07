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
print("\n".join(bad[:20]) or "no leftover names")
sys.exit(1 if bad else 0)
