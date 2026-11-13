"""What gruntly says to the child, on top of the child harness's own system prompt and tools (which are never replaced):
the task, the few rules the harness cannot know (which files, which check, no git), and the retry/handoff messages."""
from __future__ import annotations

HANDOFF_FILE = ".gruntly-handoff.md"


def _where(cwd) -> str:
    """The child's folder by its absolute path. A worktree's `.git` file names the checkout it came from, and a model that found that path (seen twice, issue #6)
    edited the person's own tree through it instead of the worktree."""
    if not cwd:
        return ""
    return (f"Your working directory is {cwd}. Read and write only inside it, with relative paths. "
            "Never use the path of any other copy of this project (the checkout this worktree came from), and never write outside this directory.\n")


def _paths(spec) -> str:
    return (f"Edit only files matching: {', '.join(spec.allowed_paths)}. "
            f"Do not touch: {', '.join(spec.deny_paths) or 'nothing extra'}.")


def preamble(spec, cwd=None) -> str:
    acc = "; ".join(a["cmd"] for a in spec.acceptance) or "the task's checks"
    return (
        "You are working in a temporary git worktree. Do only the task below.\n"
        f"{_where(cwd)}"
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


def research(spec, cwd=None) -> str:
    return (f"{_where(cwd)}"
            "You are working in a temporary git worktree that is only for reading. Answer the question below with your tools: "
            "read files, run commands, search or fetch the web. Do not change any file. Reply with the answer only, as short "
            "facts, and give the source (file path or URL) for each. If you cannot find or reach something, say so; never guess.\n\n"
            f"QUESTION:\n{spec.brief}")


def _rules(rules: str) -> str:
    return f"\n\nRULES THE PERSON SET FOR THIS PROJECT (follow them):\n{rules}" if rules.strip() else ""


def first(spec, rules: str = "", cwd=None) -> str:
    if getattr(spec, "kind", "code") == "research":
        return research(spec, cwd) + _rules(rules)
    c = f"\nStart with: {', '.join(spec.context_files)}" if spec.context_files else ""
    return f"{preamble(spec, cwd)}{_rules(rules)}\n\nTASK:\n{spec.brief}{c}"


NARRATED = "narrated"        # the pseudo-gate of a run that described its change instead of making it


def retry(spec, gate: str, output: str, handoff: str = "", guidance: str = "", context_hit: bool = False) -> str:
    if gate == NARRATED:
        parts = ["Your previous reply said the work was done, but you made no edit calls and no file changed. Describing a "
                 "change does nothing. Make the change with REAL tool calls (edit or write), then run the check.",
                 f"Your last reply:\n{output}", _paths(spec)]
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


def resume_fresh(spec, gate: str, output: str, handoff: str = "", guidance: str = "", context_hit: bool = False,
                 rules: str = "", cwd=None) -> str:
    """For children that cannot resume: the failure plus the full task."""
    return retry(spec, gate, output, handoff, guidance, context_hit) + "\n\n" + first(spec, rules, cwd)


def continuation(spec, handoff: str, guidance: str, rules: str = "", cwd=None) -> str:
    parts = [first(spec, rules, cwd)]
    if handoff:
        parts.append(f"A previous run was cut off. Its notes:\n{handoff}")
    if guidance:
        parts.append(f"Guidance from the supervisor:\n{guidance}")
    parts.append("The worktree already holds that run's partial changes. Continue; do not start over.")
    return "\n\n".join(parts)
