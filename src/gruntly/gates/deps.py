from __future__ import annotations

import re
from pathlib import Path

from .. import worktree as wtmod

MANIFESTS = re.compile(
    r"(^|/)(package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|npm-shrinkwrap\.json|"
    r"poetry\.lock|uv\.lock|Pipfile(\.lock)?|pyproject\.toml|setup\.py|setup\.cfg|requirements[^/]*\.txt|"
    r"Cargo\.(toml|lock)|go\.(mod|sum)|Gemfile(\.lock)?|composer\.(json|lock)|pom\.xml|build\.gradle(\.kts)?)$"
)


def check(spec, wt: Path, base: str) -> dict:
    hits = [p for p in wtmod.name_status(wt, base) if MANIFESTS.search(p)]
    return {"ok": not hits, "files": hits[:10]} if hits else {"ok": True}
