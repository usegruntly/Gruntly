# Contributing

Thank you for looking. gruntly is small enough that a pull request with a clear reason and a test is usually all it takes.

## Set up

```
git clone https://github.com/usegruntly/Gruntly && cd Gruntly
uv venv && uv pip install -e ".[dev,mcp]"      # Python 3.11 or newer
.venv/bin/python -m pytest -q                  # .venv\Scripts\python on Windows
```

The suite needs no model, no API key and no network: fake model servers and fake child CLIs stand in for them (`gruntly/probe.py`, `tests/fake_child/`). It takes a few minutes. Tests that drive a real harness binary skip themselves when it is not installed; to run one, point its variable at the executable (`GRUNTLY_TEST_CODEX`, `GRUNTLY_TEST_GEMINI`, `GRUNTLY_TEST_AIDER`, `GRUNTLY_TEST_HERMES_HOME`). A test must never start a paid Claude call or open a browser tab; `tests/conftest.py` guards both.

`gruntly demo` is the quickest way to see the whole flow. `python scripts/prerelease_check.py` must stay clean (no keys, no personal paths or emails).

## What helps most

- **A bug report with `gruntly --version`, your OS, the harness and its version, and the provider.** Output of `gruntly doctor` helps; remove anything private first.
- **A fix with a test that fails without it.** Behaviour in `docs/architecture.md` is deliberate; if a change touches it, say why in the pull request.
- **A harness or provider that works.** Providers are entries in `src/gruntly/data/providers.toml` (a user can also add one in `~/.config/gruntly/providers.toml`). A harness is an adapter in `src/gruntly/adapters/` (child) and `src/gruntly/parents/` (parent); `docs/adapters.md` and `docs/parents.md` say what each must report. Mark what you checked against the real program and what you only read in its documentation, as the existing rows do.
- **Setup steps for an editor or agent** that `docs/mcp-clients.md` does not cover or gets wrong.

## Conventions

- One-line commit messages that say what changed and why it matters.
- Keep the result block small: a passing run is about 300 bytes and that is a feature.
- Do not add a dependency without a reason; the only required one is PyYAML.
- Python 3.11 is the oldest supported version: no f-string that repeats its own quote character or holds a backslash inside the braces.
