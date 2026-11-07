"""Child prompts: standard preamble + brief, and the retry/handoff prompts."""
from __future__ import annotations

from dataclasses import dataclass

HANDOFF_FILE = ".gruntly-handoff.md"


def _paths(spec) -> str:
    return (f"Edit only files matching: {', '.join(spec.allowed_paths)}. "
            f"Do not touch: {', '.join(spec.deny_paths) or 'nothing extra'}.")


def preamble(spec) -> str:
    acc = "; ".join(a["cmd"] for a in spec.acceptance) or "the task's checks"
    return (
        "You are working in a temporary git worktree. Do only the task below.\n"
        f"{_paths(spec)}\n"
        "Do not run git commit, git push, or change git config.\n"
        "Do not install packages unless the task says so.\n"
        f"Before you finish, run: {acc}.\n"
        "If it passes, stop and reply with a three-line summary.\n"
        "If you are blocked, stop and say why in three lines.\n"
        f"If your context is running out before you can finish, write {HANDOFF_FILE}: files you read, "
        "what you understood, what is done, what remains. Then stop."
    )


@dataclass
class Ctx:
    """What the profile adds to a prompt: the resolved profile and the current text of the files to show."""
    profile: object = None
    inline: str = ""


def _slim(spec, ctx: Ctx) -> str:
    rp = ctx.profile
    acc = "; ".join(a["cmd"] for a in spec.acceptance) or "the task's checks"
    lines = [_paths(spec)]
    if rp.rewrite_only:
        lines.append("Rewrite each file you change in full; do not send partial edits.")
    if rp.self_check:
        lines.append(f"Check your work by running exactly this and nothing else: {acc}. If it passes, reply with two lines saying what you changed.")
    else:
        lines.append("Do not run tests. Make your edits and finish your turn: the system runs the tests and sends you "
                     "the errors if they fail. Reply with two lines saying what you changed.")
    lines.append("No git. Do not install packages. If you are blocked, say why in two lines.")
    if rp.name == "worker":
        lines.append("Look around only as much as you need. State any assumption you had to make in your final message. "
                     f"If your context runs out, write {HANDOFF_FILE} (files read, understood, done, remaining) and stop.")
    return "\n".join(lines)


def first(spec, ctx: Ctx | None = None) -> str:
    if ctx is None or ctx.profile is None or ctx.profile.name == "default":
        c = f"\nStart with: {', '.join(spec.context_files)}" if spec.context_files else ""
        return f"{preamble(spec)}\n\nTASK:\n{spec.brief}{c}"
    body = f"{_slim(spec, ctx)}\n\nTASK:\n{spec.brief}"
    return body + (f"\n\n{ctx.inline}" if ctx.inline else "")


def retry(spec, gate: str, output: str, handoff: str = "", guidance: str = "", context_hit: bool = False,
          ctx: Ctx | None = None) -> str:
    slim = ctx is not None and ctx.profile is not None and ctx.profile.name != "default"
    if slim and not ctx.profile.self_check:
        parts = [f"The system ran the checks and '{gate}' failed. Output:\n{output}",
                 "Fix the code and finish your turn. Do not run tests.", _paths(spec)]
    else:
        parts = [f"Your previous attempt did not pass the '{gate}' check. Fix only that.",
                 f"Last output:\n{output}", _paths(spec)]
    if handoff:
        parts.append(f"Notes from the previous run (it may have been cut off):\n{handoff}")
    if guidance:
        parts.append(f"Guidance from the supervisor:\n{guidance}")
    if context_hit:
        parts.append("Your context window is small: read few files, only what you need.")
    return "\n\n".join(parts)


def resume_fresh(spec, gate: str, output: str, handoff: str = "", guidance: str = "",
                 context_hit: bool = False, ctx: Ctx | None = None) -> str:
    """For children that cannot resume: the failure plus the full task, with files re-read from the worktree."""
    return retry(spec, gate, output, handoff, guidance, context_hit, ctx) + "\n\n" + first(spec, ctx)


def continuation(spec, handoff: str, guidance: str, ctx: Ctx | None = None) -> str:
    parts = [first(spec, ctx)]
    if handoff:
        parts.append(f"A previous run was cut off. Its notes:\n{handoff}")
    if guidance:
        parts.append(f"Guidance from the supervisor:\n{guidance}")
    parts.append("The worktree already holds that run's partial changes. Continue; do not start over.")
    return "\n\n".join(parts)
