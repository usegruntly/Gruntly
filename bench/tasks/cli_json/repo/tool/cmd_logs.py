"""The `logs` command."""

def collect():
    return {'lines': ['start', 'work', 'done']}


def render(data):
    return "\n".join(f"{k}: {v}" for k, v in data.items())
