"""The `config` command."""

def collect():
    return {'debug': False, 'retries': 3}


def render(data):
    return "\n".join(f"{k}: {v}" for k, v in data.items())
