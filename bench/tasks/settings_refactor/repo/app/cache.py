import os


def ttl() -> int:
    return int(os.environ.get("APP_CACHE_TTL", "60"))
