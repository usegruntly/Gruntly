# Lean agent on long tasks: what was missing (2026-11-08)

Tasks: `bugs_batch` (six modules, six bugs) and `cli_json` (feature in a CLI with no test covering the file). One run each per round, Sonnet parent, Qwen3.5-9B child. Alone-arm reference: ~$0.075 and ~17 s per run, both pass. Three rounds with fixes between them. This is n=1 per round and I fixed things I saw in the same two tasks, so the last round is not a clean test.

| round | bugs_batch | cli_json |
|---|---|---|
| 1 (before fixes) | fail, $0.052, 9 turns, 244 s | fail, $0.025, 3 turns: refused (no covering test), no fallback |
| 2 | fail, $0.042, 5 turns, 302 s | pass, $0.047, 9 turns, 540 s |
| 3 (stuck-gate fixes) | fail, $0.030, 4 turns, 305 s | pass, $0.036, 5 turns, 416 s |
| 4 (prompt) | fail, $0.031, 3 turns, 221 s | pass, $0.017, 2 turns, 108 s |

## Issues found, most critical first
1. **Request naming several files was refused** (matches > 3 files). Fixed: `agent-run` splits it into one run per file inside one call, one combined block.
2. **No covering test = refusal** (`cli_json`). Fixed: run against the whole existing suite, the child adds its own test file, and the block says no test failed before the change.
3. **`--continue` on an older run failed the scope gate** ("main tree modified") once other runs had been applied. Fixed: the baseline restarts on continue.
4. **Child's own new test file tripped the test-weakening gate** on follow-ups. Fixed: `tests_writable` for that mode.
5. **Lean Claude polished the child's tests** in follow-ups, costing minutes and breaking passing work. Prompt now forbids style/tidy follow-ups.
6. **Reviewer noticed a gap and only mentioned it** (`merge_intervals` touching intervals; the hidden test expects them merged). Prompt now says to fix a noticed gap with a follow-up. Not yet re-measured.
7. **`gruntly discard` crashed on Windows** when a dying child still held files. Now retries once and never raises.
8. **Child strips apostrophes** in word counting (rounds 1-2); the prompt now tells the reviewer to check this. Round 4 kept them. This is tuned to what I saw in this task.

## Still open
- Wall time: 100-540 s against ~17 s alone. Cost is lower (about 45-75% below alone), but the local model is slow and serial.
- `bugs_batch` has not passed on lean yet; its visible tests do not pin the edge cases, so correctness rests on the reviewer reading diffs.
- Hermes still has no child trace.
