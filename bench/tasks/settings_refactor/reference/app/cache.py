from .config import load


def ttl() -> int:
    return load().cache_ttl
