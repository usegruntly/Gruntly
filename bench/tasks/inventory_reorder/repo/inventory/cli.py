from .service import Inventory


def run(argv: list, path) -> str:
    inv = Inventory(path)
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "add":
            p = inv.add(args[0], int(args[1]), float(args[2]))
            return f"{p.name}: {p.quantity}"
        if cmd == "remove":
            p = inv.remove(args[0], int(args[1]))
            return f"{p.name}: {p.quantity}"
        if cmd == "value":
            return f"{inv.total_value():.2f}"
        if cmd == "list":
            return "\n".join(inv.names()) or "empty"
    except (ValueError, KeyError) as e:
        return f"error: {e}"
    return f"error: unknown command {cmd}"
