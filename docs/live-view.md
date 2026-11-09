# Seeing what the child is doing

A delegated run can take minutes. Claude Code only shows the command and then the result, so gruntly records a live feed.

**What is recorded.** `.gruntly/runs/<id>/progress.jsonl`, one line per event, with three actors:
- `child`: the local/small model: its tool calls (read, edit, run, with a short label such as a path or the start of a command), one line of what it says, and each model call.
- `gruntly`: its own steps: run started, attempt started, checks passed or failed, waiting on a provider's rate limit, finished.
- The parent (Claude) is not in the feed: its steps are already in the chat.

Short labels, plus `diff` rows: gruntly reads the child's worktree every couple of seconds (with a throwaway copy of the index, so the child's own git state is untouched) and writes the changes so far, capped at 40 lines of 140 characters, as valid unified-diff hunks per file. The Claude Code view draws them under the command with its own diff highlighter, like Claude's own edits (gutters, markers, add and remove colours): the latest state while running, and the last diff of each attempt when it ends, marked if that attempt failed the checks. It works for every harness because it reads the files, not the harness's output. `gruntly watch` prints each attempt's final diff. Free text and diff lines go through the same redaction as the logs. The feed is for people: it is not
added to the result block the parent reads, so it costs the parent nothing.

**In any terminal:** `gruntly watch` (latest run) or `gruntly watch RUN_ID`, coloured (cyan child, yellow gruntly); `--no-follow` prints what exists.

**In Claude Code:** plugin 0.5.0 ships a small mod that polls the feed once a second while a `gruntly ...` Bash command runs and draws
the last few events under that command's row (cyan `child`, yellow `gruntly`), plus the latest event on the status line. Install or update
the plugin and run `/reload-plugins`. The mod hooks `tool.call` for Bash only when the command is a gruntly command, and its hook is
guarded so a bug in it can never block the command.
