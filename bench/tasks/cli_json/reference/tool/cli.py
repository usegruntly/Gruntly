"""Dispatcher. Commands that support --json are listed in JSON_COMMANDS and share the same code path."""
import importlib
import json
import sys

JSON_COMMANDS = {"status", "list", "show", "stats", "users"}


def run(argv):
    if not argv:
        raise SystemExit("usage: tool <command> [--json]")
    cmd, flags = argv[0], argv[1:]
    mod = importlib.import_module(f"tool.cmd_{cmd}")
    data = mod.collect()
    if "--json" in flags:
        if cmd not in JSON_COMMANDS:
            raise SystemExit(f"--json is not supported for {cmd}")
        return json.dumps(data, sort_keys=True)
    return mod.render(data)


if __name__ == "__main__":
    print(run(sys.argv[1:]))
