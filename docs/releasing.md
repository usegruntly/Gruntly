# Releasing

A checklist for the maintainer. Nothing here runs by itself except `.github/workflows/release.yml`, which does its work when a version tag is pushed.

## One-time setup

1. **PyPI.** Make an account with two-factor sign-in. The name `gruntly` was free on 2026-11-13; check again (`https://pypi.org/project/gruntly/` should be a 404). On https://pypi.org/manage/account/publishing/ add a *pending publisher*: project `gruntly`, owner `usegruntly`, repository `Gruntly`, workflow `release.yml`, environment `pypi`. After that no token is needed anywhere.
2. **GitHub.** Settings, Environments, create `pypi` (optionally require yourself as a reviewer, so a tag cannot publish unattended). Settings, Code security: turn on *Private vulnerability reporting* (SECURITY.md and the issue template point to it). Actions are free on a public repository; on a private one the macOS runner costs ten minutes for each minute used.
3. **Your commit identity.** Use GitHub's noreply address for commits that will be public: `git config user.email "ID+LOGIN@users.noreply.github.com"` (the ID is on https://api.github.com/users/LOGIN). In GitHub, Settings, Emails: turn on *Keep my email addresses private* and *Block command line pushes that expose my email*.

## Before the repository becomes public

1. `python scripts/prerelease_check.py --history` must print `clean`. **Done on 2026-11-13**: the one real address (in the author and committer of every commit, and the tagger of the four tags) was replaced by the GitHub noreply address with `git filter-repo --mailmap`, after checking that all 134 commits kept identical trees and messages, and `main` and the tags were force-pushed. A fresh clone of GitHub passes the check. Two things remain true:
   - GitHub keeps the old commits reachable by their full hash for a while, to anyone who has access to the repository. While it is private that is only you and your collaborators; if you want certainty before it goes public, publish from a *fresh* repository (second option below) instead of flipping this one.
   - Your global git identity (`git config --global user.email`) is still the real address, so commits in your *other* repositories will carry it. This repository has the noreply address set locally. Set the global one too, and turn on *Keep my email addresses private* and *Block command line pushes that expose my email* in GitHub's email settings.

   For the record, the steps that were used (and that work again if a real address ever gets back in). Two ways out:
   - **Rewrite the history** (every clone must be made again afterwards, and the old commits stay visible in anyone's fork or cache made while the repository was public, so do this *before* the switch). Work on a copy:
     ```
     # mailmap.txt, one line:  Your Name <ID+LOGIN@users.noreply.github.com> <the-old-address@example.org>
     pip install git-filter-repo
     git clone --mirror https://github.com/usegruntly/Gruntly gruntly-clean.git
     cd gruntly-clean.git && git filter-repo --mailmap ../mailmap.txt
     python ../Gruntly/scripts/prerelease_check.py --root <a normal clone of it> --history
     git push --force --mirror https://github.com/usegruntly/Gruntly
     ```
   - **Or publish a fresh repository** from a squashed history and keep this one private.
2. Read `docs/` once as a stranger would. It holds working notes (`investigation-*.md`, `plan-*.md`, `research-brief.md`) and measured benchmark data (`docs/benchmarks/`, including `delegation-export/`, which is derived from your own Claude Code sessions: numbers and labels only, but your call). Remove or keep each deliberately.
3. `LICENSE` names the copyright holder; `pyproject.toml` names the author. Both say what you want public.
4. The README's logo uses relative paths: fine on GitHub, broken on PyPI. Once public, change the two `docs/brand/svg/...` URLs in the top block to `https://raw.githubusercontent.com/usegruntly/Gruntly/main/docs/brand/svg/...`.
5. Push and watch the first CI run (Linux and Windows). **macOS has never run the suite and is not part of CI**: its minutes cost ten times as much on a private repository, so it is checked by hand (next section) and the `test-macos` job in `ci.yml` only runs when you start it yourself.

## Testing on a Mac

Ask someone with a Mac to open Terminal and paste this (about 10 minutes, no account or key needed):

```
curl -LsSf https://astral.sh/uv/install.sh | sh        # skip if uv is installed
git clone https://github.com/usegruntly/Gruntly && cd Gruntly
uv venv --python 3.12 && uv pip install -e ".[dev,mcp]"
.venv/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tail -40
.venv/bin/gruntly demo
```

What to send back: the last lines of the pytest output (the `passed` / `failed` line and any `FAILED` names), the output of `gruntly demo`, and `sw_vers` and `uname -m`. Failures are expected to be about paths (macOS temp folders are symbolic links) or the shell; each is a small fix. If it all passes, record the macOS version and date in `CHANGELOG.md` and the README's Status section.

## Each release

1. Move the *Unreleased* part of `CHANGELOG.md` under the new version, set `version` in `pyproject.toml`, commit.
2. CI is green on `main`.
3. `git tag v0.4.0 && git push origin v0.4.0`. The workflow checks that the tag matches `pyproject.toml`, runs the file scan, builds the wheel and sdist, runs `twine check`, installs the *wheel* on Linux and Windows and runs `gruntly demo` from an unrelated folder, and only then publishes.
4. `gh release create v0.4.0 --notes-file <the changelog section>`.
5. From a clean machine or folder: `uvx gruntly@latest --version` and `uvx gruntly@latest demo`.

## After the first release

- **MCP registry.** The official registry verifies a PyPI package by a line in its README of the form `mcp-name: io.github.usegruntly/gruntly`. Generate `server.json` with the registry's own tool (`mcp-publisher init`) rather than writing it by hand, as the schema changes.
- **Claude Code plugin.** `/plugin marketplace add usegruntly/Gruntly` works as soon as the repository is public.
- Announce where your users are, with the demo and the honest numbers: delegating pays on long tasks and loses on short ones (`docs/where-delegation-wins.md`).
