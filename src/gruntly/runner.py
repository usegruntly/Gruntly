"""Run orchestration: queue, worktree, child process with limits, gates, retries, escalation."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import doctor, prompt, result as resmod, sandbox, worktree as wtmod
from .apply import apply_run
from .adapters.base import get_adapter, scrub_env
from .gates import acceptance, deps, diff_size, scope, test_weakening
from .redact import redact, secrets_from_env
from .spec import Spec
from .store import Store

OUTPUT_CAP = 8_000_000
MALFORMED_LIMIT = 5
INFRA = re.compile(r"(?i)(ECONNREFUSED|connection refused|fetch failed|connection error|"
                   r"max retries exceeded|no route to host|name or service not known)")
CONTEXT = re.compile(r"(?i)(context[ _-]?(length|window)|maximum context|n_ctx|exceeds the (available )?context|"
                     r"too many tokens|token limit)")
GATE_PRIORITY = ["scope", "test_weakening", "new_deps", "diff_size", "acceptance", "holdout", "regression", "lint", "typecheck"]
RISKY_PATH = re.compile(r"(?i)(auth|secur|crypt|secret|passw|token|migrat|\.env|\.lock$|dockerfile|\.github/)")
REVIEW_LINES = 150


# ---------------------------------------------------------------- child process
@dataclass
class ChildRun:
    stdout: str
    stderr: str
    exit_code: int | None
    breach: str | None  # wall | idle | output | None
    secs: float


def _tree_mtime(path: Path, limit: int = 20000) -> float:
    newest, n = 0.0, 0
    for dp, dn, fn in os.walk(path):
        dn[:] = [d for d in dn if d not in (".git", "node_modules", "__pycache__", ".pytest_cache")]
        for f in fn:
            try:
                newest = max(newest, os.stat(os.path.join(dp, f)).st_mtime)
            except OSError:
                pass
            n += 1
            if n >= limit:
                return newest
    return newest


def run_child(adapter, argv, env, stdin, cwd: Path, wall_s: float, idle_s: float) -> ChildRun:
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    t0 = time.monotonic()
    proc = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    bufs = {"out": [], "err": []}
    state = {"last": time.monotonic(), "size": 0}

    def pump(stream, key):
        for chunk in iter(lambda: stream.read1(65536), b""):
            bufs[key].append(chunk)
            state["size"] += len(chunk)
            state["last"] = time.monotonic()

    def feed():
        try:
            proc.stdin.write(stdin.encode("utf8"))
            proc.stdin.close()
        except OSError:
            pass

    threads = [threading.Thread(target=pump, args=(proc.stdout, "out"), daemon=True),
               threading.Thread(target=pump, args=(proc.stderr, "err"), daemon=True)]
    if stdin is not None:
        threads.append(threading.Thread(target=feed, daemon=True))
    for t in threads:
        t.start()
    breach, last_scan, mt = None, 0.0, _tree_mtime(cwd)
    while proc.poll() is None:
        now = time.monotonic()
        if now - t0 > wall_s:
            breach = "wall"
        elif state["size"] > OUTPUT_CAP:
            breach = "output"
        elif now - state["last"] > idle_s:
            breach = "idle"
        if breach:
            adapter.cancel(proc)
            break
        if now - last_scan > 3:
            last_scan = now
            new = _tree_mtime(cwd)
            if new > mt:
                mt, state["last"] = new, now
        time.sleep(0.1)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        adapter.cancel(proc)
    for t in threads:
        t.join(timeout=2)
    dec = lambda k: b"".join(bufs[k]).decode("utf8", "replace")  # noqa: E731
    return ChildRun(dec("out"), dec("err"), proc.returncode, breach, round(time.monotonic() - t0, 1))


# ---------------------------------------------------------------- queue
def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_slot(root: Path, max_conc: int, stale_s: float, wait_s: float = 3600) -> Path:
    d = root / ".gruntly" / "locks"
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    while True:
        for i in range(max(1, max_conc)):
            p = d / f"slot{i}.lock"
            try:
                fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return p
            except FileExistsError:
                try:
                    pid = int(p.read_text() or 0)
                    if not _pid_alive(pid) or time.time() - p.stat().st_mtime > stale_s:
                        p.unlink(missing_ok=True)
                except (OSError, ValueError):
                    pass
        if time.time() - t0 > wait_s:
            holders = []
            for q in d.glob("slot*.lock"):
                try:
                    holders.append(f"pid {q.read_text().strip()} for {int(time.time() - q.stat().st_mtime)}s")
                except OSError:
                    pass
            raise TimeoutError(f"queue busy: another run holds the only slot ({', '.join(holders) or 'unknown'}); "
                               f"waited {int(wait_s)}s")
        time.sleep(1)


# ---------------------------------------------------------------- gates
def _failing_text(name: str, g: dict) -> str:
    if name == "holdout":  # the child sees which holdout tests failed, never their bodies or assertion text
        names = [ln.strip()[:160] for ln in g.get("tail", "").splitlines() if ln.startswith("FAILED ")]
        return "\n".join(names) or "holdout check failed (no test names available)"
    if name == "acceptance" or name in ("regression", "lint", "typecheck"):
        return g.get("tail", "")
    return "\n".join(g.get("violations") or g.get("findings") or g.get("problems") or g.get("files") or [name])


def run_gates(spec: Spec, wt: Path, base: str, root: Path, main_fp: str, secrets: list[str]) -> dict:
    g: dict = {}
    on = spec.gates
    g["scope"] = scope.check(spec, wt, base, root, main_fp) if on.get("scope", True) else {"ok": True, "skipped": True}
    g["diff_size"] = diff_size.check(spec, wt, base)
    g["test_weakening"] = test_weakening.check(spec, wt, base) if on.get("no_test_weakening", True) else {"ok": True, "skipped": True}
    g["new_deps"] = deps.check(spec, wt, base) if on.get("no_new_deps", True) else {"ok": True, "skipped": True}
    a = acceptance.check(spec, wt)
    g["acceptance"] = {"ok": a["ok"], "cmd": a["cmd"], "tail": "" if a["ok"] else
                       resmod.tail_lines(redact(a["output"], secrets), resmod.GATE_TAIL_LINES)}
    for extra in ("regression", "lint", "typecheck"):
        cmd = on.get(extra)
        if cmd:
            r = acceptance.run_cmd(cmd, wt, 300)
            g[extra] = {"ok": r["ok"], "cmd": cmd, "tail": "" if r["ok"] else
                        resmod.tail_lines(redact(r["output"], secrets), resmod.GATE_TAIL_LINES)}
    if spec.holdout:
        g["holdout"] = _holdout_gate(spec.holdout, wt, root, secrets)
    return g


def _holdout_gate(h: dict, wt: Path, root: Path, secrets: list[str]) -> dict:
    """Copy the parent's held-out tests in, run them, remove them. The child never sees them."""
    copied: list[Path] = []
    try:
        for rel in h["files"]:
            src, dst = root / rel, wt / rel
            if not src.is_file():
                return {"ok": False, "tail": f"holdout file missing: {rel}"}
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            copied.append(dst)
        r = acceptance.run_cmd(h["cmd"], wt, 300)
        return {"ok": r["ok"], "cmd": h["cmd"], "tail": "" if r["ok"] else
                resmod.tail_lines(redact(r["output"], secrets), resmod.GATE_TAIL_LINES)}
    finally:
        for f in copied:
            f.unlink(missing_ok=True)


def first_failure(gates: dict) -> str | None:
    for n in GATE_PRIORITY:
        if n in gates and not gates[n]["ok"]:
            return n
    return None


def diff_stat(wt: Path, base: str) -> dict:
    rows = wtmod.numstat(wt, base)
    return {"files": len(rows), "insertions": sum(a or 0 for _, a, _ in rows),
            "deletions": sum(d or 0 for _, _, d in rows), "paths": [p for p, _, _ in rows][:20]}


# ---------------------------------------------------------------- orchestration
def prepare(spec: Spec, root: Path, run_id: str | None = None) -> str:
    from .spec import new_run_id
    rid = run_id or spec.id or new_run_id()
    Store(root, rid).create({**spec.to_dict(), "id": rid})
    return rid


def execute(root: Path, run_id: str, guidance: str | None = None, extra_attempts: int | None = None) -> dict:
    st = Store.existing(root, run_id)
    spec = Spec(**st.read_json("spec.json"))
    if extra_attempts:
        spec.max_attempts = extra_attempts
    t_start = time.monotonic()
    try:
        slot = acquire_slot(root, spec.max_concurrency, spec.budget_s + 600, wait_s=min(spec.budget_s, 3600))
    except TimeoutError as e:
        return _finish(st, spec, root, "error", 0, {}, {"files": 0, "insertions": 0, "deletions": 0, "paths": []},
                       "", None, t_start, 0.0, 0.0, {"available": False}, error=str(e))
    try:
        return _execute(st, spec, root, run_id, guidance, t_start)
    finally:
        slot.unlink(missing_ok=True)


def _execute(st: Store, spec: Spec, root: Path, run_id: str, guidance: str | None, t_start: float) -> dict:
    empty = {"files": 0, "insertions": 0, "deletions": 0, "paths": []}
    cont = guidance is not None
    prior = st.read_json("state.json", {}) if cont else {}
    if cont and not (root / ".gruntly" / "worktrees" / run_id).is_dir():
        return _finish(st, spec, root, "error", 0, {}, empty, "", None, t_start, 0, 0, {"available": False},
                       error="worktree is gone; nothing to continue")
    st.set_state("running")
    adapter = get_adapter(spec.harness)

    # infrastructure preflight: never spend an attempt on a down server
    if spec.harness != "generic":
        det = adapter.detect()
        if not det.installed:
            return _finish(st, spec, root, "error", 0, {}, empty, "", None, t_start, 0, 0, {"available": False},
                           error=det.detail)
        p = doctor.probe_endpoint(spec.endpoint)
        if not p["ok"]:
            return _finish(st, spec, root, "error", 0, {}, empty, "", None, t_start, 0, 0, {"available": False},
                           error=p["error"])
        if spec.model and spec.model not in p["models"]:
            return _finish(st, spec, root, "error", 0, {}, empty, "", None, t_start, 0, 0, {"available": False},
                           error=f"model {spec.model!r} not loaded on the server; available: {p['models']}")
        ctx = p["ctx"].get(spec.model) if spec.model else (next(iter(p["ctx"].values()), None))
        if ctx:
            st.set_state("running", ctx=ctx)
            if ctx < spec.min_context and not spec.allow_small_ctx:
                return _finish(st, spec, root, "error", 0, {}, empty, "", None, t_start, 0, 0, {"available": False},
                               error=f"model context is {ctx} tokens (< {spec.min_context}): the agent's own prompt "
                                     f"nearly fills it and runs fail. Reload the model with a larger context, or set "
                                     f"allow_small_ctx: true to run anyway.")

    if cont:
        base, main_fp = prior["base"], prior["main_fp"]
        wt = root / ".gruntly" / "worktrees" / run_id
    else:
        main_fp = wtmod.fingerprint(root)
        w = wtmod.create(root, run_id, spec.base, exclude=(spec.holdout or {}).get("files"))
        base, wt = w.base, w.path
    attempt_no = prior.get("attempts", 0)
    session = prior.get("session")
    handoff_path = wt / prompt.HANDOFF_FILE

    child_s = gates_s = 0.0
    attempts_log: list[dict] = prior.get("attempts_log", [])
    last_sig, last_gate, last_text = None, None, ""
    usage = {"available": False}
    summary = ""
    context_hit = False
    status, error, gates = "escalate", None, {}
    reason = "attempts exhausted"
    caps = adapter.capabilities()
    warnings: list[str] = list(prior.get("warnings", []))
    if not cont and spec.kind == "code":
        # red before green: if acceptance already passes at the base, it proves nothing about the child's work
        if acceptance.check(spec, wt)["ok"]:
            warnings.append("acceptance already passes before any change: it cannot prove the task was done")

    for local in range(1, spec.max_attempts + 1):
        attempt_no += 1
        remaining = spec.budget_s - (time.monotonic() - t_start)
        if remaining <= 5:
            status, reason = "timeout", "wall-clock budget used up"
            break
        notes = redact(handoff_path.read_text(encoding="utf8", errors="replace"), [])[:1500] if handoff_path.exists() else ""
        if local == 1:
            text = prompt.continuation(spec, notes, guidance) if cont else prompt.first(spec)
        elif caps.resume and session:
            text = prompt.retry(spec, last_gate, last_text, notes, "", context_hit)
        else:
            text = prompt.resume_fresh(spec, last_gate, last_text, notes, "", context_hit)
        cmd = adapter.command(spec, wt, text, session if (local > 1 and caps.resume) else None)
        try:
            cmd = sandbox.wrap(cmd, spec.sandbox_level, wt, root, spec.endpoint)
        except RuntimeError as e:
            return _finish(st, spec, root, "error", attempt_no - 1, gates, empty, summary, None, t_start,
                           child_s, gates_s, usage, error=str(e))
        env = scrub_env(cmd.env, spec.env_allow)
        secrets = secrets_from_env(env)
        st.set_state("running", attempt=attempt_no)
        cr = run_child(adapter, cmd.argv, env, cmd.stdin, wt, min(remaining, spec.budget_s), spec.no_progress_s)
        child_s += cr.secs
        st.append_text("child.log", redact(f"\n=== attempt {attempt_no} exit={cr.exit_code} breach={cr.breach} ===\n"
                                           f"{cr.stdout}\n--- stderr ---\n{cr.stderr}\n", secrets))
        out = adapter.parse(cr.stdout, cr.stderr, cr.exit_code if cr.exit_code is not None else -1)
        summary = redact(out.final_message, secrets)
        session = out.session_id or session
        if out.usage.get("available"):
            usage = out.usage
        context_hit = bool(CONTEXT.search(cr.stderr + out.final_message))

        if cr.breach:
            status = "timeout"
            reason = {"wall": "wall-clock budget exceeded", "idle": f"no progress for {spec.no_progress_s}s",
                      "output": "child output size cap exceeded"}[cr.breach]
            st.write_text(f"attempts/{attempt_no}/diff.patch", redact(wtmod.patch(wt, base), secrets))
            break
        stats = diff_stat(wt, base)
        if cr.exit_code not in (0, None) and INFRA.search(cr.stderr + cr.stdout) and stats["files"] == 0:
            status, error = "error", "model server error during run: " + redact(resmod.tail_lines(cr.stderr or cr.stdout, 3), secrets)
            break

        st.set_state("gating", attempt=attempt_no)
        tg = time.monotonic()
        gates = run_gates(spec, wt, base, root, main_fp, secrets)
        gates_s += time.monotonic() - tg
        st.write_text(f"attempts/{attempt_no}/diff.patch", redact(wtmod.patch(wt, base), secrets))
        for n, g in gates.items():
            st.write_text(f"attempts/{attempt_no}/gate_{n}.txt", redact(_failing_text(n, g), secrets))
        failed = first_failure(gates)
        attempts_log.append({"n": attempt_no, "files": stats["files"], "ins": stats["insertions"],
                             "del": stats["deletions"], "failed_gate": failed})
        if failed is None:
            status = "passed"
            break
        last_gate = failed
        last_text = resmod.tail_lines(redact(_failing_text(failed, gates[failed]), secrets), resmod.BUNDLE_LINES)
        sig = (failed, hashlib.sha1(re.sub(r"\d+(\.\d+)?", "N", last_text).encode()).hexdigest())
        if out.malformed_calls >= MALFORMED_LIMIT:
            reason = f"child made {out.malformed_calls} malformed tool calls"
            break
        if sig == last_sig:
            reason = f"stuck: gate '{failed}' failed identically twice"
            break
        last_sig = sig

    stats = diff_stat(wt, base)
    bundle = None
    if status in ("escalate", "timeout"):
        bundle = {"reason": reason, "gate": last_gate, "files_touched": stats["paths"], "attempts": attempts_log[-4:]}
        if context_hit:
            bundle["context_exhausted"] = True
    notes = redact(handoff_path.read_text(encoding="utf8", errors="replace")[:1500], []) \
        if status in ("escalate", "timeout") and handoff_path.exists() else ""
    st.write_json("state.json", {"base": base, "main_fp": main_fp, "attempts": attempt_no, "session": session,
                                 "attempts_log": attempts_log, "warnings": warnings})
    applied = hint = None
    if status == "passed":
        hint = _review_hint(gates, stats, warnings)
        if spec.apply_on_pass:
            applied = apply_run(root, st, spec, base, main_fp)
            if applied.get("applied"):
                wtmod.remove(root, run_id)  # the patch is in the user's tree; keep only the run record
            else:
                status = "escalate"
                bundle = {"reason": applied.get("error", "apply failed"), "gate": "apply",
                          "files_touched": stats["paths"], "attempts": attempts_log[-4:]}
                last_text = applied.get("gate_output") or "\n".join(
                    applied.get("violations") or applied.get("conflicts") or [])
    return _finish(st, spec, root, status, attempt_no, gates, stats, summary, bundle, t_start, child_s, gates_s,
                   usage, error=error, last_text=last_text, handoff=notes, applied=applied, review_hint=hint,
                   warnings=warnings)


def _review_hint(gates: dict, stats: dict, warnings: list[str]) -> list[str]:
    """When the parent should look at the diff. Empty means the gates are enough."""
    hint = []
    lines = stats["insertions"] + stats["deletions"]
    if lines > REVIEW_LINES:
        hint.append(f"large diff ({lines} lines)")
    risky = [x for x in stats["paths"] if RISKY_PATH.search(x)]
    if risky:
        hint.append("touches sensitive paths: " + ", ".join(risky[:3]))
    if warnings:
        hint.append("weak acceptance: " + warnings[0])
    return hint


def _finish(st, spec, root, status, attempts, gates, stats, summary, bundle, t_start, child_s, gates_s, usage,
            error=None, last_text="", handoff="", applied=None, review_hint=None, warnings=None) -> dict:
    rid = st.run_id
    applied = applied or {}
    ok_applied = bool(applied.get("applied"))
    if status == "passed" and ok_applied:
        nxt = []
    elif status == "passed":
        nxt = [f"gruntly apply {rid}"] + ([f"gruntly diff {rid} --stat"] if review_hint else [])
    elif status in ("escalate", "timeout"):
        nxt = [f"gruntly diff {rid} --stat", f'gruntly continue {rid} --guidance "<what to do differently>"',
               f"gruntly discard {rid}"]
    else:
        nxt = ["gruntly doctor"]
    untrusted = None
    if status != "passed":
        untrusted = {k: v for k, v in {
            "gate_output": resmod.tail_lines(last_text, resmod.BUNDLE_LINES) if last_text else "",
            "handoff": handoff, "summary": resmod.head_chars(summary, resmod.SUMMARY_CHARS)}.items() if v}
    res = resmod.build(run_id=rid, status=status, attempts=attempts, gates=gates, diff_stat=stats,
                       failure_bundle=bundle, wall_s=round(time.monotonic() - t_start),
                       child_tokens=(usage or {}).get("total_tokens"), next_cmds=nxt, untrusted=untrusted,
                       applied=ok_applied if applied else None, verify=applied.get("verify"),
                       review_hint=review_hint, warnings=warnings, error=error)
    st.save_result(res, meta={"wall_s": res["wall_s"], "child_usage": usage})
    return res
