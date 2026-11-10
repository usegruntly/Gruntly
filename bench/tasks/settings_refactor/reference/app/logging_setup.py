from .config import load


def level() -> str:
    return load().log_level
