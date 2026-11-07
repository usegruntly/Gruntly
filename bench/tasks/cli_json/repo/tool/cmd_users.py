"""The `users` command."""

def collect():
    return {'users': [{'name': 'ann', 'role': 'admin'}, {'name': 'bo', 'role': 'dev'}]}


def render(data):
    return "\n".join(f"{k}: {v}" for k, v in data.items())
