"""The `stats` command."""

def collect():
    return {'count': 12, 'mean': 3.5}


def render(data):
    return "\n".join(f"{k}: {v}" for k, v in data.items())
