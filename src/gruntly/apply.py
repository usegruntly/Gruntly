"""Apply a run's patch to the user's working tree. Never commits.

verify: the gates already ran the acceptance command on exactly this content in the worktree. If the
main tree has not changed since the run began, that result still holds ("unchanged"). If it has, the
patch landed on different code, so acceptance is re-run in the main tree; a failure there reverses the
patch instead of leaving a broken tree ("failed").
"""
from __future__ import annotations

from pathlib import Path

from . import worktree as wtmod
from .gates import acceptance, scope
from .redact import redact
from .result import tail_lines
from .store import Store


def apply_run(root: Path, st: Store, spec, base: str, main_fp: str, branch: str | None = None) -> dict:
    wt = root / ".gruntly" / "worktrees" / st.run_id
    if not wt.is_dir():
        return {"applied": False, "error": "worktree is gone; nothing to apply"}
    if spec.gates.get("scope", True):
        sc = scope.check(spec, wt, base, root, None)  # the parent may have edited files since the run began
        if not sc["ok"]:
            return {"applied": False, "error": "scope gate failed at apply", "violations": sc["violations"]}
    patch = wtmod.patch(wt, base)
    if not patch.strip():
        return {"applied": False, "error": "empty diff"}
    files = [r[0] for r in wtmod.numstat(wt, base)]
    moved = wtmod.fingerprint(root) != main_fp
    if branch:
        wtmod.git(["switch", "-c", branch], root)
    pf = st.dir / "apply.patch"
    pf.write_bytes(patch.encode("utf8"))
    p = wtmod.git(["apply", "--whitespace=nowarn", str(pf)], root, check=False)
    three_way = False
    if p.returncode != 0:
        three_way = True
        p = wtmod.git(["apply", "--3way", "--whitespace=nowarn", str(pf)], root, check=False)
    if p.returncode != 0:
        conflicts = wtmod.git(["diff", "--name-only", "--diff-filter=U"], root, check=False).stdout.split()
        return {"applied": False, "error": "conflict", "conflicts": conflicts, "detail": p.stderr.strip()[-600:],
                "note": "worktree kept; resolve by hand or discard"}
    verify = "unchanged"
    if moved or three_way:
        r = acceptance.check(spec, root, purge=False)
        if not r["ok"]:
            wtmod.git(["apply", "-R", "--whitespace=nowarn", str(pf)], root, check=False)
            return {"applied": False, "verify": "failed", "files": files,
                    "error": "acceptance failed in the main tree after applying; patch reversed",
                    "gate_output": redact(tail_lines(r["output"], 20), [])}
        verify = "ok"
    return {"applied": True, "verify": verify, "files": files}
