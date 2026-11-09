"""The pickers (`gruntly use`, `gruntly models`) and the first-run guide (`gruntly setup`).

The rule behind all of it: gruntly shows what the account and the endpoint report, and the person decides. It does not rank
models, hide any, or claim one is free: it prints the provider's docs links at every step where that matters.
"""
from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

from . import keys, models as modelsmod, providers
from . import settings_file
from .spec import global_config_path

LOCAL_DEFAULT_ENDPOINT = "http://127.0.0.1:1234/v1"


# ------------------------------------------------------------------------------------------------------ small helpers
def interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask(prompt: str, default: str = "") -> str:
    try:
        v = input(prompt).strip()
    except EOFError:
        return default
    return v or default


def say(text: str = "") -> None:
    print(text, flush=True)


def print_docs(name: str) -> None:
    links = providers.docs_for(name)
    if links:
        say("  Docs:")
        for label, url in links:
            say(f"    {label}: {url}")


def mark_path() -> Path:
    return global_config_path().parent / "onboarded"


def is_onboarded() -> bool:
    return mark_path().is_file()


def project_config() -> Path | None:
    from . import worktree as wtmod
    try:
        return wtmod.repo_root(Path.cwd()) / ".gruntly.toml"
    except Exception:  # noqa: BLE001 - not in a git repository
        return None


def current_choice() -> tuple[str, str | None, str]:
    """(provider, model, where it comes from) as the settings files say today."""
    for label, p in (("this project", project_config()), ("your global settings", global_config_path())):
        if p and p.is_file():
            prov = settings_file.get_value(p, "provider")
            model = settings_file.get_value(p, "model")
            if prov or model:
                return prov or "local", model, label
    return "local", None, "the defaults"


# ------------------------------------------------------------------------------------------------------ harnesses
def current_harness() -> tuple[str, str]:
    for label, p in (("this project", project_config()), ("your global settings", global_config_path())):
        if p and p.is_file():
            h = settings_file.get_value(p, "harness")
            if h:
                return h, label
    return "auto", "the defaults"


def show_harness(h, fetch: bool = False, current: str | None = None, number: int | None = None) -> None:
    from . import harnesses
    ok, ver = harnesses.installed(h.name) if h.name != "generic" else (True, None)
    state = "installed" + (f" {ver}" if ver else "") if ok else "not installed"
    head = f"{number}. " if number else ""
    say(f"  {head}{h.title}  [{state}]" + ("  (current)" if h.name == current else ""))
    say(f"       {h.good_at}")
    say(f"       Weight: {h.cost}")
    if not ok:
        say(f"       Install: {h.install}")
    say(f"       Docs: {h.docs}")
    if fetch:
        d = harnesses.live_description(h)
        if d:
            say(f"       Their own words (GitHub): {d}")


def choose_harness(current: str | None = None, fetch: bool = False) -> str | None:
    from . import harnesses
    names = list(harnesses.HARNESSES)
    say("\nWhich child agent should do the work? (auto = the first installed of opencode, qwen, hermes)")
    for i, n in enumerate(names, 1):
        show_harness(harnesses.HARNESSES[n], fetch, current, i)
    while True:
        v = ask("Number or name, a = auto (Enter to cancel): ")
        if not v:
            return None
        if v.lower() in ("a", "auto"):
            return "auto"
        if v.isdigit() and 1 <= int(v) <= len(names):
            return names[int(v) - 1]
        if v in names:
            return v
        say("  Not one of the options.")


def save_harness(harness: str, scope: str | None = None) -> Path:
    proj = project_config()
    path = global_config_path() if scope == "global" or proj is None else proj
    settings_file.set_values(path, {"harness": None if harness == "auto" else harness})
    return path


# ------------------------------------------------------------------------------------------------------ providers
def provider_status(name: str) -> str:
    if name == "local":
        from . import doctor
        up = doctor.probe_endpoint(LOCAL_DEFAULT_ENDPOINT, timeout=1.5)["ok"]
        try:
            n = f"{len(modelsmod.fetch('local', LOCAL_DEFAULT_ENDPOINT))} downloaded model(s)"
        except modelsmod.ModelsError:
            n = "no models found"
        return f"LM Studio: {n}; server at {LOCAL_DEFAULT_ENDPOINT} " + ("running" if up else "not running (start it in LM Studio)")
    p = providers.get(name)
    _, src = keys.lookup(name, p.key_env)
    return f"{p.note or name}: " + (f"key found ({src})" if src else "no key yet")


def ensure_key(name: str) -> bool:
    """Make sure a hosted provider has a key; offer to enter one. True when a working key exists afterwards."""
    p = providers.get(name)
    key, src = keys.lookup(name, p.key_env)
    if key:
        return True
    if not interactive():
        say(f"No API key for {name}. Run `gruntly auth set {name}` or set {p.key_env}.")
        return False
    say(f"\n{name} needs an API key.")
    print_docs(name)
    entered = getpass.getpass(f"  Paste your {name} API key (hidden, Enter to skip): ").strip()
    if not entered:
        return False
    try:
        locked = keys.set_key(name, entered)
    except ValueError as e:
        say(f"  Not saved: {e}")
        return False
    say(f"  Saved to {keys.keys_path()}" + (" (readable by you only)." if locked else " (plain text: keep that file private)."))
    try:
        n = len(modelsmod.fetch(name))
        say(f"  Key works: the account lists {n} models.")
    except modelsmod.ModelsError as e:
        say(f"  Saved, but a test request failed: {e}")
    return True


def choose_provider(current: str | None = None) -> str | None:
    names = ["local"] + list(providers.PROVIDERS)
    say("\nWhich model provider should gruntly use for the child agent?")
    for i, n in enumerate(names, 1):
        mark = "  (current)" if n == current else ""
        say(f"  {i}. {n:<8} {provider_status(n)}{mark}")
    while True:
        v = ask("Number or name (Enter to cancel): ")
        if not v:
            return None
        if v.isdigit() and 1 <= int(v) <= len(names):
            return names[int(v) - 1]
        if v in names:
            return v
        say("  Not one of the options.")


# ------------------------------------------------------------------------------------------------------ models
def show_models(name: str, ms: list[modelsmod.Model], number: bool = False) -> None:
    for i, m in enumerate(ms, 1):
        say(("  %3d. " % i if number else "  ") + modelsmod.line(m))


def choose_model(name: str, endpoint: str, current: str | None = None) -> str | None:
    """Show every model the account offers, as reported by the endpoint, and let the person pick one."""
    try:
        ms = modelsmod.fetch(name, endpoint)
    except modelsmod.ModelsError as e:
        say(f"\nCould not list models for {name}: {e}")
        return ask("Type a model id to use anyway (Enter to skip): ") or None
    default = None
    if name != "local" and name in providers.PROVIDERS:
        default = providers.PROVIDERS[name].default_model
    default = current if current and any(m.id == current for m in ms) else default
    if name == "local":
        say(f"\nlocal: {len(ms)} model(s) downloaded in LM Studio, whether loaded or not. Pick one; load it in LM Studio (or with `lms load`).")
    else:
        say(f"\n{name}: {len(ms)} model(s), exactly as the endpoint lists them.")
        say("A listing does not say which models are free or usable on your account: check the docs below.")
    print_docs(name)
    shown = ms
    while True:
        say()
        show_models(name, shown, number=True)
        hint = f", Enter = {default}" if default else ""
        v = ask(f"\nNumber, model id, or text to filter the list{hint}, q = cancel: ", default or "")
        if v.lower() == "q" or v == "":
            return default if v == "" and default else None
        if v.isdigit() and 1 <= int(v) <= len(shown):
            return shown[int(v) - 1].id
        exact = [m for m in ms if m.id == v]
        if exact:
            return exact[0].id
        hits = [m for m in ms if v.lower() in m.id.lower() or v.lower() in json.dumps(m.info).lower()]
        if not hits:
            say(f"  Nothing matches {v!r}. Showing the full list again.")
            shown = ms
        else:
            say(f"  {len(hits)} match {v!r}:")
            shown = hits


# ------------------------------------------------------------------------------------------------------ saving
def save_choice(provider: str, model: str | None, scope: str | None = None) -> Path:
    """Write provider and model to the project's .gruntly.toml (inside a repository) or the global settings."""
    proj = project_config()
    if scope == "global" or proj is None:
        path = global_config_path()
    else:
        path = proj
    settings_file.set_values(path, {"provider": provider if provider != "local" else None, "model": model})
    return path


def choose_scope() -> str:
    if project_config() is None:
        return "global"
    v = ask("Save this for [p]this project or [g]all your projects? (p/g, Enter = p): ", "p").lower()
    return "global" if v.startswith("g") else "project"


# ------------------------------------------------------------------------------------------------------ first run
FEATURES = """\
What gruntly does
  Your paid model (Claude) hands small, test-backed coding tasks to a cheaper model: a local one, or one on a hosted
  endpoint. gruntly runs it in a throwaway git worktree, checks the result (tests, scope, diff size, no weakened tests,
  no new dependencies), retries if needed, and returns a compact result. Nothing is committed for you.

Commands worth knowing
  gruntly agent-run 'task'          delegate a change (Claude calls this through the plugin)
  gruntly agent-run --ask 'q'       a lookup with the child's own tools (web, shell, files); nothing is changed
  gruntly watch                     live view of what the child is doing
  gruntly use                       change provider or model        gruntly models   list what an account offers
  gruntly auth set|list|remove      API keys, kept in a private file, never in a project
  gruntly doctor                    check git, the child CLI, the model server and your keys
  gruntly guide                     the full manual
"""


def setup() -> int:
    if not interactive():
        say("`gruntly setup` is an interactive guide: run it in a terminal.")
        return 2
    say("Welcome to gruntly: hand the grunt work to a cheaper model.\n")
    say("Step 1 of 3: the child agent")
    import shutil
    say(f"  git: {'found' if shutil.which('git') else 'MISSING (gruntly needs git)'}")
    harness = choose_harness(current_harness()[0])
    scope = choose_scope()
    if harness is not None:
        say(f"  Saved to {save_harness(harness, scope)}: harness = {harness}")

    say("\nStep 2 of 3: where the child's model runs")
    provider = choose_provider(current_choice()[0])
    if provider is None:
        say("Skipped. Run `gruntly setup` or `gruntly use` any time.")
        return 0
    if provider != "local" and not ensure_key(provider):
        say(f"No key, so {provider} was not set up. Run `gruntly auth set {provider}` when you have one.")
        return 0
    if provider == "local":
        say("  Local models: load one in LM Studio with a context of 16k or more (32k for the full agent), and start its server.")
        print_docs("local")
    say("\nStep 3 of 3: which model")
    model = choose_model(provider, LOCAL_DEFAULT_ENDPOINT, current_choice()[1])
    if provider == "local" and model is None:
        say("  No model chosen: gruntly will use whichever model is loaded in the local server.")
    path = save_choice(provider, model, scope)
    say(f"\nSaved to {path}: provider = {provider}, model = {model or 'whatever is loaded'}.")
    mark = mark_path()
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text("done\n", encoding="utf8")
    say("\n" + FEATURES)
    say("Next steps")
    say("  1. gruntly doctor")
    say("  2. In Claude Code:  /plugin marketplace add usegruntly/Gruntly   then   /plugin install gruntly@gruntly")
    say("  3. Ask Claude to make a small change; it will delegate it.")
    print_docs(provider)
    return 0


def first_run_offer() -> bool:
    """`gruntly` typed with no arguments in a terminal for the first time: offer the guide."""
    if is_onboarded() or not interactive():
        return False
    say("This looks like your first time with gruntly.")
    if ask("Run the 5-minute setup guide now? [Y/n]: ", "y").lower().startswith("n"):
        mark = mark_path()
        mark.parent.mkdir(parents=True, exist_ok=True)
        mark.write_text("skipped\n", encoding="utf8")
        say("OK. `gruntly setup` runs it any time; `gruntly --help` lists the commands.")
        return True
    setup()
    return True
