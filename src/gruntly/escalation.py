"""A child that cannot fix a task: noticing it early, saying why, and deciding whether a stronger model should take over.

Three separate things, all counted from what the child did and not from what it says about itself:

  Stall      progress is a diff the child has not produced before. Reading for ever, running the same test again and again, or
             editing and reverting are not progress, so none of them keeps a run alive for ever.
  classify   why a run that did not pass did not pass: stuck (loop, stall, the same failure twice), hard (it tried and the
             check still fails), gave_up (it touched nothing), slow (the time ran out with a partial diff).
  recommend  the policy: `[escalate] when = "off" | "hard"` in .gruntly.toml (or GRUNTLY_ESCALATE). Off by default: until the
             benchmark's escalation A/B says the extra cost buys enough correct work, the result only records the class.

Escalation is meant to be rare: only when it is apparent the child will not get there. One failed run is not that (a follow-up
with precise guidance sometimes finishes it); a second round that fails again is. A run that merely ran out of time while still
changing the code is not either. And "escalate" means one thing: the task goes to a full session of the caller's own model with
the normal system prompt and tools. It is not a second child and not a chain.
"""
from __future__ import annotations

import hashlib
import os
import time
import tomllib
from pathlib import Path

WHEN = ("off", "hard")
HARD = {"stuck", "hard", "gave_up"}          # a class the policy may act on; "slow" never is: it was still changing the code
MIN_ROUNDS = 2                               # the child has been run, given guidance and run again
REVISITS = 3                     # a diff that returns to an earlier state this many times is going round in circles
EMPTY = hashlib.sha1(b"").hexdigest()


def digest(patch: str) -> str:
    return hashlib.sha1(patch.encode("utf8", "replace")).hexdigest()


class Stall:
    """Watches one number: how long since the child last produced a diff it had not produced before."""

    def __init__(self, stall_s: float, first_edit_s: float, now: float | None = None, start: str = EMPTY):
        """`start` is the diff the attempt begins with: an earlier attempt's work is the baseline, not progress."""
        self.stall_s, self.first_edit_s = stall_s, first_edit_s
        self.t0 = self.last_new = time.monotonic() if now is None else now
        self.seen = {EMPTY, start}
        self.last = start
        self.edited = start != EMPTY
        self.revisits = 0

    def observe(self, state: str, now: float | None = None) -> str | None:
        """`state` is digest(current patch). Returns a breach name (loop, stall, noedit) or None."""
        now = time.monotonic() if now is None else now
        if state != self.last:
            if state in self.seen:
                self.revisits += 1
            else:
                self.seen.add(state)
                self.last_new = now
            if state != EMPTY:
                self.edited = True
            self.last = state
        if self.revisits >= REVISITS:
            return "loop"
        if self.edited and self.stall_s and now - self.last_new > self.stall_s:
            return "stall"
        if not self.edited and self.first_edit_s and now - self.t0 > self.first_edit_s:
            return "noedit"
        return None


def when(root: Path | None) -> str:
    """The policy: GRUNTLY_ESCALATE, else `[escalate] when` of the project's .gruntly.toml, else off."""
    v = os.environ.get("GRUNTLY_ESCALATE", "").strip().lower()
    if not v and root is not None:
        p = Path(root) / ".gruntly.toml"
        try:
            v = str((tomllib.loads(p.read_text(encoding="utf8")).get("escalate") or {}).get("when", "")).lower() if p.is_file() else ""
        except (tomllib.TOMLDecodeError, OSError):
            v = ""
    return v if v in WHEN else "off"


STUCK_BREACHES = {"loop", "stall", "noedit", "calls", "idle", "output"}


def classify(status: str, reason: str | None, breach: str | None = None, files: int = 0, attempts: int = 1) -> dict | None:
    """Why a run that did not pass did not pass. None when there is nothing to classify (passed, running, a server error)."""
    if status not in ("escalate", "timeout"):
        return None
    why = (reason or status)[:160]
    r = (reason or "").lower()
    if breach in STUCK_BREACHES or r.startswith("stuck:") or "malformed" in r:
        cls = "stuck"
    elif breach == "wall" or "budget used up" in r:
        cls = "slow" if files > 0 else "stuck"
    elif files == 0 or "narrated work" in r:
        cls = "gave_up"
    else:
        cls = "hard"
    return {"class": cls, "why": why, "attempts": attempts, "files": files}


def recommend(cls: str, policy: str, rounds: int) -> bool:
    """Rare on purpose: policy `hard`, a class that says the child cannot get there, and a second round already spent."""
    return policy == "hard" and cls in HARD and rounds >= MIN_ROUNDS
