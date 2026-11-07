"""The `jobs` command."""

def collect():
    return {'queued': 2, 'running': 1}


def render(data):
    return "\n".join(f"{k}: {v}" for k, v in data.items())
