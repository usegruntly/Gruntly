from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _checkout_version() -> str | None:
    """An editable install keeps the version it had on the day it was installed (the user's `gruntly --version` said 0.2.1 while the code was
    0.3.0). When this file sits in a source checkout, that checkout's pyproject.toml is the truth."""
    try:
        import tomllib
        p = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if p.is_file():
            meta = tomllib.loads(p.read_text(encoding="utf8")).get("project") or {}
            if meta.get("name") == "gruntly" and isinstance(meta.get("version"), str):
                return meta["version"]
    except Exception:  # noqa: BLE001 - the version is a label; never fail an import over it
        pass
    return None


try:
    __version__ = _checkout_version() or version("gruntly")
except PackageNotFoundError:        # run from a source tree that was never installed
    __version__ = "0+unknown"
