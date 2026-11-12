"""Facts about how much of the request a child's change covers, counted from the request and the diff alone (no model).

A small model is a poor judge of whether it has finished, and so is a parent that may not read the code. What a reader
can do is count: how many parts the request lists against how many files changed, which files it names that the diff never
touched, which names it asks for that exist nowhere, whether only a changelog changed. Each fact is a short line for the
`flags:` of the result block; none of them says the change is wrong, they say where to look.
"""
from __future__ import annotations

import builtins
import keyword
import os
import re
from pathlib import Path

from . import do
from . import worktree as wtmod

MAX_FACTS = 4
STRONG = {"docs_only", "parts", "many", "names"}        # gaps that say the request is not covered; "named" may be a mere reference
MAX_NAMES = 5
NON_CODE = (".md", ".rst", ".txt", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".json", ".lock")
BUILTIN = set(dir(builtins)) | set(keyword.kwlist)
MANY = re.compile(r"\b(?:every|each|all)\s+(?:other\s+)?(?:module|file|command|place|caller|call site)s?\b"
                  r"|\ball over\b|\beverywhere\b|\bthroughout\b|\bacross the\b", re.I)


def patch_files(patch: str) -> list[str]:
    """Paths the patch touches (the `b/` side), in order, without duplicates."""
    return list(dict.fromkeys(m.group(1) for m in re.finditer(r"^diff --git a/\S+ b/(\S+)", patch, re.M)))


def added_text(patch: str) -> str:
    return "\n".join(l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))


NOT_A_PART = {"note", "notes", "example", "examples", "important", "warning", "why", "reason", "context", "intended", "tip"}


def parts(request: str) -> int:
    """How many parts the request lists: numbered (1) (2) (3), `1.` or `2)` at the start of a line, lettered (A) (B), or
    labelled sections (`Storage: ... API: ... CLI: ...`, which a model writes just as often as a numbered list)."""
    nums = set(re.findall(r"\((\d{1,2})\)", request)) | set(re.findall(r"(?m)^\s*(\d{1,2})[.)]\s", request))
    letters = {x.upper() for x in re.findall(r"\(([A-Za-z])\)", request)}
    labels = {x.lower() for x in re.findall(r"(?:^|[.!?]\s+|\n)\s*([A-Z][A-Za-z]{1,14}):\s", request)} - NOT_A_PART
    return max(len(nums), len(letters), len(labels))


def named_paths(request: str, files: list[str]) -> list[str]:
    """Tracked, non-test files the request names by path (or by a path ending that matches exactly one file)."""
    out: list[str] = []
    for p in do.candidates(request)[2]:
        hit = [f for f in files if f == p or f.endswith("/" + p)]
        if len(hit) == 1 and not do.is_test_path(hit[0]) and hit[0] not in out:
            out.append(hit[0])
    return out


def code_names(request: str) -> list[str]:
    """Names that look like code: a lone backticked word or flag, snake_case, CamelCase, CONSTANT_NAMES. Plain English and the
    language's own names (ValueError, True, ...) are left out, because they exist everywhere and would flag nothing real."""
    found: list[str] = []
    for m in re.finditer(r"`([^`\n]+)`", request):
        s = m.group(1).strip()
        if re.fullmatch(r"-{1,2}[A-Za-z][\w-]*", s):
            found.append(s)
        elif re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\(\))?", s):      # `word`, `a.b`, `f()`: not a path or a usage line
            found += re.findall(r"[A-Za-z_]\w*", s)[-1:]
    found += re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", request)
    found += re.findall(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b", request)
    found += re.findall(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b", request)
    out: list[str] = []
    for n in found:
        if len(n) >= 4 and n.lower() not in do.GENERIC and n not in BUILTIN and n not in out:
            out.append(n)
    return out


def in_tree(name: str, root: Path) -> bool:
    """Is the name anywhere in the working tree (tracked or not)? A name the request asks for that is neither here nor in the diff
    was never created."""
    p = wtmod.git(["grep", "-I", "-q", "-w", "-F", "--untracked", "-e", name], root, check=False)
    return p.returncode == 0


def cumulative_patch(root: Path, base: str) -> str:
    """Everything changed in the tree since `base`, as one patch, new files included (git diff alone leaves untracked files out). The
    work of every round so far, which is what the original request has to be measured against once there has been a follow-up."""
    out = wtmod.git(["diff", base, "--", "."], root, check=False).stdout
    new = wtmod.git(["ls-files", "-o", "--exclude-standard"], root, check=False).stdout.split("\n")
    for f in [x.strip() for x in new if x.strip() and not x.startswith(".gruntly/")][:200]:
        try:
            body = (Path(root) / f).read_text(encoding="utf8", errors="replace")
        except OSError:
            continue
        out += f"diff --git a/{f} b/{f}\nnew file mode 100644\n--- /dev/null\n+++ b/{f}\n" + "".join(f"+{ln}\n" for ln in body.splitlines()[:400])
    return out


def facts(request: str, patch: str, root: Path) -> list[str]:
    """Short lines, at most MAX_FACTS, for a request and the patch a child produced against it. Empty when nothing stands out."""
    return [t for _, t in gaps(request, patch, root)]


def gaps(request: str, patch: str, root: Path) -> list[tuple[str, str]]:
    """The same, as (kind, text) pairs: docs_only, parts, named, many, names."""
    if not request.strip() or not patch.strip():
        return []
    touched = patch_files(patch)
    files = do.tracked(root)
    src = [f for f in touched if not do.is_test_path(f) and not f.endswith(NON_CODE)]
    out: list[tuple[str, str]] = []

    names = code_names(request)
    docs_only = bool(touched) and not src and not any(do.is_test_path(f) for f in touched)
    if docs_only and names:
        out.append(("docs_only", f"the diff changes only non-code files ({', '.join(touched[:3])}) but the request is about code "
                                 f"({', '.join(names[:3])})"))

    n = parts(request)
    if n >= 3 and len(src) <= 1 and not docs_only:
        where = f" ({src[0]})" if src else ""
        out.append(("parts", f"the request lists {n} parts and the diff touches {len(src)} source file{'' if len(src) == 1 else 's'}{where}: "
                             "check that every part is in the diff"))

    missing = [f for f in named_paths(request, files) if f not in touched]
    if missing:
        out.append(("named", "the request names " + ", ".join(missing[:3]) + " and the diff does not touch " +
                    ("it" if len(missing) == 1 else "them") + " (fine if it was only a reference)"))

    if MANY.search(request) and src:
        dirs = {os.path.dirname(f) for f in src}
        every = [f for f in files if f.endswith(".py") and not do.is_test_path(f) and os.path.dirname(f) in dirs]
        if len(every) >= 3 and len(src) * 2 < len(every):
            out.append(("many", f"the request is about many modules and the diff touches {len(src)} of {len(every)} source files "
                                f"in {', '.join(sorted(d or '.' for d in dirs))}"))

    added = added_text(patch)
    absent = [x for x in names if x not in added and not in_tree(x, root)]
    if absent:
        out.append(("names", "the request names " + ", ".join(absent[:MAX_NAMES]) + ", which the diff never adds and the repo does not contain"))
    return out[:MAX_FACTS]
