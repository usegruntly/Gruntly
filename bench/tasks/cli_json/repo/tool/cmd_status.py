"""The `status` command."""

def collect():
    return {'state': 'ok', 'uptime': 42}


def render(data):
    return "\n".join(f"{k}: {v}" for k, v in data.items())
