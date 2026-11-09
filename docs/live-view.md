# Seeing what the child is doing

A delegated run can take minutes. Claude Code only shows the command and then the result, so gruntly records a live feed.

**What is recorded.** `.gruntly/runs/<id>/progress.jsonl`, one line per event, with three actors:
- `child`: the local/small model: its tool calls (read, edit, run, with a short label such as a path or the start of a command), one line of what it says, and each model call.
- `gruntly`: its own steps: run started, attempt started, checks passed or failed, waiting on a provider's rate limit, finished.
- The parent (Claude) is not in the feed: its steps are already in the chat.

Labels only: no file contents or diffs, and free text goes through the same redaction as the logs. The feed is for people: it is not
added to the result block the parent reads, so it costs the parent nothing.

**In any terminal:** `gruntly watch` (latest run) or `gruntly watch RUN_ID`, coloured (cyan child, yellow gruntly); `--no-follow` prints what exists.

**In Claude Code:** plugin 0.5.0 ships a small mod that polls the feed once a second while a `gruntly ...` Bash command runs and draws
the last few events under that command's row (cyan `child`, yellow `gruntly`), plus the latest event on the status line. Install or update
the plugin and run `/reload-plugins`. The mod hooks `tool.call` for Bash only when the command is a gruntly command, and its hook is
guarded so a bug in it can never block the command.
