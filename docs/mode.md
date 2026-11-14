# Switching gruntly on and off

Three modes, so nobody has to say "use gruntly" or "don't use gruntly" in every chat:

| Mode | What happens |
|---|---|
| `auto` | The default. The skill decides when delegating pays. |
| `on` | Claude delegates every eligible change without asking first. "Eligible" is still the skill's rules: a bounded change where the file can be named, tests exist or the change is mechanical. Small edits go too: the "~8+ turns" rule belongs to `auto` and does not apply here (a run costs the big agent a turn or two more than a one-line edit by hand; that is the choice `on` makes). Design, security and wide investigation stay with Claude. |
| `off` | gruntly refuses new work with one line (`status: refused ... switched OFF ...`) and Claude does everything itself. `wait`, `apply`, `diff` and `discard` still work, so a run already in flight can be finished. |

**Where it is set** (most specific wins): the environment variable `GRUNTLY_MODE`, then this Claude Code **session**, then this **project**, then `auto`.
Project is the default scope. Both are plain files under `.gruntly/`, which git ignores, so a mode is personal and never ends up in a commit.

```
/gruntly:mode on            # works everywhere the plugin is installed; /gruntly:gruntly on does the same
/gruntly                    # in Claude Code: show the mode
/gruntly on                 # this project
/gruntly off session        # only this chat
/gruntly follow session     # this chat goes back to following the project
gruntly mode                # the same from a terminal (show)
gruntly mode on|off|auto [--session]
```

Two ways to type it in Claude Code: `/gruntly on` is the mod's own command (needs plugin 0.6+ loaded; try `/reload-plugins`), and
`/gruntly:mode on` or `/gruntly:gruntly on` run the CLI directly (`gruntly mode ...`), so they work even if the mod is not loaded.
Both need the updated CLI (`uv tool install --reinstall "gruntly[mcp] @ git+https://github.com/usegruntly/Gruntly"`).

**How it is enforced.** The CLI refuses `agent-run`, `run` and `do` (including `--ask` and `--continue`) while the mode is `off`, whichever
agent calls it. In Claude Code the plugin also adds a short line to the system prompt when the mode is `on` or `off`
(about 40 tokens, nothing in `auto`) and shows `gruntly ON` or `gruntly OFF` above the prompt.
