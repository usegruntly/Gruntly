from .config import load


def enabled() -> list:
    return list(load().features)
