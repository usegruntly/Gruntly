# Security policy

## Reporting a vulnerability

Please report it privately: on this repository open the **Security** tab and choose **Report a vulnerability**. Do not open a public issue for a vulnerability. Include what you did, what you expected and what happened, the version (`gruntly --version`) and your operating system.

Only the latest release is supported while gruntly is at 0.x.

## What gruntly protects, and what it does not

gruntly runs another program (the child agent) on your code, usually with that program's auto-approve switches on, so that it can work without asking you. Read this section before you point it at anything sensitive.

**What it does**
- The child works in a separate git worktree, not in your checkout. Nothing reaches your tree until you (or your agent, with `--apply-on-pass`) apply it, and gruntly never commits.
- The child gets a scrubbed environment: no `ANTHROPIC_*`, `OPENAI_*`, cloud or GitHub tokens from your shell. For a hosted provider the child is given a placeholder key and a local proxy adds the real one, so the real key is not in the child's environment or in its logs.
- Before and after a run gruntly fingerprints your working tree. If the child changed it, the run fails (`main tree modified`), and `gruntly restore RUN` puts back only the files that are still as the child left them.
- Gates check the result (scope, diff size, weakened or deleted tests, new dependencies, your acceptance command) before your agent sees a pass.
- Everything the child wrote (its summary, test output, notes) comes back under an `untrusted` key and is marked as data. Your agent must never follow instructions found there; the skill and the MCP instructions say so.
- API keys are kept in `~/.config/gruntly/keys.toml`, created readable by you only (on Windows the inherited permissions are removed). They are never printed, and run logs are redacted.
- gruntly itself has no telemetry and sends nothing anywhere except to the model endpoint you chose (and, for `gruntly models` and `gruntly verify`, to the provider you ask about). The harnesses it launches (OpenCode, Qwen Code, Codex, Gemini CLI, Hermes, Aider and so on) have their own settings for analytics and update checks; gruntly turns off the ones it knows about (Aider's, for example) and cannot speak for the rest.

**What it does not do**
- **Sandbox level 0 (the default) is not a security boundary.** A child with shell access can read and write anything your user account can, including files outside the repository, and it can make network requests. The worktree and the fingerprint detect and limit accidents; they do not stop a hostile or badly behaved model. Run gruntly on code and machines where that is acceptable.
- **Sandbox level 1** (`sandbox_level = 1`) uses bubblewrap to make everything except the worktree read-only. It is Linux only and has had little live testing. There is no sandbox on Windows or macOS.
- **The local model proxy and the Gemini and Codex bridges listen on 127.0.0.1 on a random port while a run is active, and do not authenticate the caller.** Another process on the same machine that finds the port could send requests through them, including requests that use your provider key. Do not run gruntly with a hosted provider on a machine shared with users you do not trust. A per-run token is planned.
- A file written outside the repository (a child that walks up out of its worktree) is reported as a warning, not undone.
- **A hosted provider sees your code.** If the child (or the parent) uses a hosted provider, the task text and the files the model reads go to that provider under its terms. A local model server keeps everything on your machine.
- **The MCP server** (`gruntly mcp`) speaks stdio only and runs `gruntly` commands as you, in the repository the client names. Treat registering it like giving that client a shell command, and keep per-call approval on for `gruntly_manage` (it can apply a patch to your working tree).

## Keys and secrets in the repository

`python scripts/prerelease_check.py` scans for key-shaped strings and personal paths and runs in CI. If you find a real credential in this repository or its history, report it as above.
