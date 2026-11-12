"""Providers a child (or a parent) can use instead of the default local model server: hosted OpenAI-compatible endpoints and
local servers, from a catalog that is data, not code.

The catalog is `data/providers.toml` in the package. `~/.config/gruntly/providers.toml` and `<project>/.gruntly/providers.toml`
add providers or override single fields of one (a later file wins field by field). A broken user file is reported
(`LOAD_WARNINGS`, shown by `gruntly providers`) and ignored; it never takes the packaged catalog down with it.

For a hosted provider the child never sees the real API key: gruntly starts a small local proxy (proxy.py) that adds the key,
spaces requests to stay inside the provider's limits and retries a 429. The child talks to http://127.0.0.1:PORT/v1 with a dummy
key. Limits are conservative defaults, not promises: providers change them, and `rate_limits` in a spec or `.gruntly.toml`
overrides them (keys: rpm, tpm, rpd). A local server needs no key and no proxy.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from importlib import resources
from pathlib import Path


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    key_env: str
    default_model: str | None
    rpm: int | None = None       # requests per minute
    tpm: int | None = None       # tokens per minute (estimated from the request size)
    rpd: int | None = None       # requests per day
    note: str = ""
    models_api: str = "openai"   # how the model list is fetched: openai (GET /models) or gemini (the native, richer listing)
    docs: tuple[tuple[str, str], ...] = ()   # (label, url) pairs shown when a person sets the key or picks a model
    kind: str = "hosted"         # hosted (needs a key, goes through the proxy) or local (a server on this machine)
    free_tier: bool = False
    verified: bool = False       # a live check has passed; False = from the provider's documentation only


_FIELDS = {f.name for f in fields(Provider)} - {"name"}
LOAD_WARNINGS: list[str] = []


def _read(text: str, where: str) -> dict:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise CatalogError(f"{where}: {e}") from None
    for name, t in data.items():
        if not isinstance(t, dict):
            raise CatalogError(f"{where}: [{name}] must be a table")
    return data


def _build(name: str, t: dict, where: str) -> Provider:
    unknown = set(t) - _FIELDS
    if unknown:
        raise CatalogError(f"{where}: [{name}] has unknown field(s) {sorted(unknown)}; known: {sorted(_FIELDS)}")
    kind = t.get("kind", "hosted")
    if kind not in ("hosted", "local"):
        raise CatalogError(f"{where}: [{name}] kind must be 'hosted' or 'local'")
    if not t.get("base_url"):
        raise CatalogError(f"{where}: [{name}] needs a base_url")
    if kind == "hosted" and not t.get("key_env"):
        raise CatalogError(f"{where}: [{name}] is hosted and needs key_env (the environment variable that holds its key)")
    for f in ("rpm", "tpm", "rpd"):
        if t.get(f) is not None and (isinstance(t[f], bool) or not isinstance(t[f], int)):
            raise CatalogError(f"{where}: [{name}] {f} must be a whole number")
    try:
        docs = tuple((str(a), str(b)) for a, b in t.get("docs", ()))
    except (TypeError, ValueError):
        raise CatalogError(f"{where}: [{name}] docs must be a list of [label, url] pairs") from None
    return Provider(name=name, base_url=str(t["base_url"]), key_env=str(t.get("key_env", "")), default_model=t.get("default_model") or None,
                    rpm=t.get("rpm"), tpm=t.get("tpm"), rpd=t.get("rpd"), note=str(t.get("note", "")),
                    models_api=str(t.get("models_api", "openai")), docs=docs, kind=kind, free_tier=bool(t.get("free_tier", False)),
                    verified=bool(t.get("verified", False)))


def user_files(root: Path | None = None) -> list[Path]:
    from .spec import global_config_path
    files = [global_config_path().parent / "providers.toml"]
    if root is not None:
        files.append(Path(root) / ".gruntly" / "providers.toml")
    return files


def load(root: Path | None = None, user: bool = True) -> dict[str, Provider]:
    """The catalog: packaged < global user file < project file, merged field by field."""
    merged: dict[str, dict] = {}
    sources = [(_read(resources.files("gruntly").joinpath("data/providers.toml").read_text(encoding="utf8"), "packaged providers.toml"),
                "packaged providers.toml")]
    if user:
        for p in user_files(root):
            if p.is_file():
                try:
                    sources.append((_read(p.read_text(encoding="utf8"), str(p)), str(p)))
                except OSError as e:
                    raise CatalogError(f"{p}: {e}") from None
    where: dict[str, str] = {}
    for data, label in sources:
        for name, t in data.items():
            merged[name] = {**merged.get(name, {}), **t}
            where[name] = label
    return {name: _build(name, t, where[name]) for name, t in merged.items()}


def _initial() -> dict[str, Provider]:
    try:
        return load()
    except CatalogError as e:
        LOAD_WARNINGS.append(f"{e}; using the packaged catalog only")
        return load(user=False)


ALL: dict[str, Provider] = _initial()
PROVIDERS: dict[str, Provider] = {n: p for n, p in ALL.items() if p.kind == "hosted"}      # hosted: what `provider = "NAME"` means
LOCAL: dict[str, Provider] = {n: p for n, p in ALL.items() if p.kind == "local"}           # local servers with a known default address


def get(name: str, root: Path | None = None) -> Provider:
    table = PROVIDERS if root is None else {n: p for n, p in load(root).items() if p.kind == "hosted"}
    try:
        return table[name]
    except KeyError:
        raise ValueError(f"unknown provider {name!r}; known: local, {', '.join(table)}") from None


def api_key(p: Provider) -> str | None:
    """The environment variable first, then the user's keys file (see keys.py)."""
    if p.kind == "local":
        return None
    from . import keys
    return keys.lookup(p.name, p.key_env)[0]


def resolve_local(provider: str, endpoint: str | None, default_endpoint: str) -> tuple[str, str | None]:
    """`provider = "ollama"` means the local provider at Ollama's address, unless the spec names its own endpoint."""
    srv = LOCAL.get(provider)
    if srv is None:
        return provider, endpoint
    return "local", (srv.base_url if endpoint in (None, default_endpoint) else endpoint)


# Shown for the local option, which is not a hosted Provider.
LOCAL_DOCS = (("LM Studio local server", "https://lmstudio.ai/docs/app/api"),
              ("Which local models and context size to use", "https://github.com/usegruntly/Gruntly/blob/main/README.md"))
GRUNTLY_DOCS = (("gruntly docs: providers, keys, limits", "https://github.com/usegruntly/Gruntly/blob/main/docs/providers.md"),
                ("gruntly repository", "https://github.com/usegruntly/Gruntly"))


def docs_for(name: str) -> tuple[tuple[str, str], ...]:
    """Links to print whenever a person sets a key or chooses a model."""
    found = PROVIDERS.get(name) or ALL.get(name)             # PROVIDERS first: it is the table other code (and tests) add to
    base = LOCAL_DOCS if name == "local" else (found.docs if found else ())
    return base + GRUNTLY_DOCS[:1]
