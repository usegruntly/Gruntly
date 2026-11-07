"""The `list` command."""

def collect():
    return {'items': ['a', 'b', 'c']}


def render(data):
    return "\n".join(f"{k}: {v}" for k, v in data.items())
