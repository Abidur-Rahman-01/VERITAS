"""Nested Path Resolver."""

def get_nested_path(data: dict, path: str, default=None):
    # BUG: Fails when an intermediate value is None or not a dict instead of returning default
    current = data
    parts = path.split(".")
    for part in parts:
        if part in current:
            if isinstance(current[part], dict):
                current = current[part]
            elif current[part] is None:
                return default
            else:
                return default
        else:
            return default
    return current
