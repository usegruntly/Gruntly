"""What gruntly says to the child, on top of the child harness's own system prompt and tools (which are never replaced):
the task, the few rules the harness cannot know (which files, which check, no git), and the retry/handoff messages."""
from __future__ import annotations

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
        "Make your changes with real tool calls: describing a step in text changes nothing.\n"
        f"Before you finish, run: {acc}.\n"
        "If it passes, stop and reply with a three-line summary.\n"
        "If you are blocked, stop and say why in three lines.\n"
        f"If your context is running out before you can finish, write {HANDOFF_FILE}: files you read, "
        "what you understood, what is done, what remains. Then stop."
    )


def research(spec) -> str:
    return ("You are working in a temporary git worktree that is only for reading. Answer the question below with your tools: "
            "read files, run commands, search or fetch the web. Do not change any file. Reply with the answer only, as short "
            "facts, and give the source (file path or URL) for each. If you cannot find or reach something, say so; never guess.\n\n"
            f"QUESTION:\n{spec.brief}")


def first(spec) -> str:
    if getattr(spec, "kind", "code") == "research":
        return research(spec)
    c = f"\nStart with: {', '.join(spec.context_files)}" if spec.context_files else ""
    return f"{preamble(spec)}\n\nTASK:\n{spec.brief}{c}"


def retry(spec, gate: str, output: str, handoff: str = "", guidance: str = "", context_hit: bool = False) -> str:
    parts = [f"Your previous attempt did not pass the '{gate}' check. Fix only that.",
             f"Last output:\n{output}", _paths(spec)]
    if handoff:
        parts.append(f"Notes from the previous run (it may have been cut off):\n{handoff}")
    if guidance:
        parts.append(f"Guidance from the supervisor:\n{guidance}")
    if context_hit:
        parts.append("Your context window is small: read few files, only what you need.")
    return "\n\n".join(parts)


def resume_fresh(spec, gate: str, output: str, handoff: str = "", guidance: str = "", context_hit: bool = False) -> str:
    """For children that cannot resume: the failure plus the full task."""
    return retry(spec, gate, output, handoff, guidance, context_hit) + "\n\n" + first(spec)


def continuation(spec, handoff: str, guidance: str) -> str:
    parts = [first(spec)]
    if handoff:
        parts.append(f"A previous run was cut off. Its notes:\n{handoff}")
    if guidance:
        parts.append(f"Guidance from the supervisor:\n{guidance}")
    parts.append("The worktree already holds that run's partial changes. Continue; do not start over.")
    return "\n\n".join(parts)
