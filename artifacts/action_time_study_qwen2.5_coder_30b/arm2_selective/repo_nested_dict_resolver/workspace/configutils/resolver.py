"""Nested Path Resolver."""

def get_nested_path(data: dict, path: str, default=None):
    # BUG: Fails when an intermediate value is None or not a dict instead of returning default
    current = data
    parts = path.split(".")
    for part in parts:
        if part not in current:
            return default
        if current[part] is None or not isinstance(current[part], dict):
            return default
        current = current[part]
    return current
