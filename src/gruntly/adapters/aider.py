"""Aider as a child (checked against 0.86.2, the real binary against a stub model server).

Aider edits the files it is shown with the model's help; it is not a tool-calling agent, so it works with small models that cannot call tools
and the whole turn count is small. gruntly points it at the endpoint it gives every child as an OpenAI-compatible model (`openai/<model>`,
`OPENAI_API_BASE`, `OPENAI_API_KEY` in the environment), gives it the task with `--message`, and keeps everything Aider would write into
the tree out of it: its chat, input and LLM history go to a private folder, the repo map (and its cache directory) is off, it is told not to
touch `.gitignore`, and nothing is committed (the change stays in the tree for gruntly's gates). Update checks and analytics are off, and so
are the pretty and streamed output (a plain, whole response also carries the usage). The parent's `plan` mode runs it as `--chat-mode ask`
(it answers, it does not edit). A session is not resumed.

Limits: with the repo map off Aider only knows the files it is told about (the brief names them, and `--yes-always` lets it add a file it
asks for), so it suits a change in named files, which is what gruntly delegates anyway.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .. import nobrowser
from ..spec import permission_mode
from .base import Caps, ChildOutcome, Command, Detection, count_malformed, kill_tree, which

TOKENS = re.compile(r"Tokens:\s*([\d.,]+)(k?)\s*sent(?:,\s*[\d.,]+k?\s*cache write)?(?:,\s*[\d.,]+k?\s*cache hit)?,\s*([\d.,]+)(k?)\s*received", re.I)
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
BANNER = ("Aider v", "Main model:", "Weak model:", "Model:", "Git repo:", "Repo-map:", "Tokens:", "You can skip this check", "Added .aider", "Creating empty file")


def _n(v: str, k: str) -> int:
    x = float(v.replace(",", ""))
    return int(round(x * 1000)) if k else int(x)


def parse_output(stdout: str) -> tuple[str, int, int, int]:
    """(the reply without Aider's banner and token lines, tokens sent, tokens received, how many token lines)."""
    out = ANSI.sub("", stdout or "")
    sent = recv = n = 0
    for m in TOKENS.finditer(out):
        sent += _n(m.group(1), m.group(2))
        recv += _n(m.group(3), m.group(4))
        n += 1
    lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith(BANNER)]
    return "\n".join(lines).strip(), sent, recv, n


class AiderAdapter:
    name = "aider"

    def detect(self) -> Detection:
        exe = which("aider")
        if not exe:
            return Detection(False, None, "aider not on PATH (python -m pip install aider-chat)")
        try:
            v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
        except Exception as e:  # noqa: BLE001
            return Detection(True, None, f"version check failed: {e}")
        return Detection(True, v.split()[-1] if v else None)

    def command(self, task, workdir: Path, prompt: str, resume: str | None) -> Command:
        model = task.model or "default"
        state = Path(workdir).parents[1] / "child-state" / Path(workdir).name / "aider"
        argv = [which("aider") or "aider", "--model", f"openai/{model}", "--message", prompt, "--yes-always", "--no-auto-commits", "--no-gitignore",
                "--no-check-update", "--no-analytics", "--no-show-model-warnings", "--no-pretty", "--no-stream", "--no-fancy-input", "--no-detect-urls",
                "--no-restore-chat-history", "--map-tokens", "0", "--chat-history-file", str(state / "chat.md"), "--input-history-file", str(state / "input"),
                "--llm-history-file", str(state / "llm.log")]
        if permission_mode(task) == "plan":
            argv += ["--chat-mode", "ask"]
        env = {"OPENAI_API_BASE": task.endpoint, "OPENAI_API_KEY": task.api_key, "PYTHONIOENCODING": "utf-8", "AIDER_ANALYTICS": "false",
               **nobrowser.env()}       # --yes-always also says yes to "Open URL for more info?" and Aider has no switch against it (gruntly/nobrowser.py)
        state.mkdir(parents=True, exist_ok=True)
        return Command(argv=argv, env=env, stdin=None)

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ChildOutcome:
        text, sent, recv, n = parse_output(stdout)
        out = ChildOutcome(malformed_calls=count_malformed(stderr, stdout))
        if exit_code != 0 or not text:
            out.is_error = True
            out.final_message = (text or stderr or "").strip()[-600:] or "no output"
        else:
            out.final_message = text[-2000:]
        if n:
            out.usage = {"available": True, "input_tokens": sent, "output_tokens": recv, "total_tokens": sent + recv, "requests": n,
                         "input_per_request": round(sent / n)}
        return out

    def capabilities(self) -> Caps:
        return Caps(resume=False, structured_output=False)

    def cancel(self, proc) -> None:
        kill_tree(proc)
