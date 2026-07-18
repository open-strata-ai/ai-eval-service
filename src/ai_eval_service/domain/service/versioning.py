from __future__ import annotations


def next_version(current: str) -> str:
    """Semantic patch bump, e.g. ``v1.2.3`` -> ``v1.2.4`` (docking §6.4)."""
    if current.startswith("v"):
        prefix, num = "v", current[1:]
    else:
        prefix, num = "", current
    parts = num.split(".")
    try:
        if len(parts) == 1:
            parts = [parts[0], "0", "0"]
        parts = [int(p) for p in parts]  # validates every segment
        parts[-1] = parts[-1] + 1
    except ValueError:
        return prefix + "1.0.0"
    return prefix + ".".join(str(p) for p in parts)
