"""The `show` command."""

def collect():
    return {'id': 7, 'title': 'demo', 'tags': ['x', 'y']}


def render(data):
    return "\n".join(f"{k}: {v}" for k, v in data.items())
