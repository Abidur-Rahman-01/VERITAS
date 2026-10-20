"""Nested Path Resolver."""

def get_nested_path(data: dict, path: str, default=None):
    # BUG: Fails when an intermediate value is None or not a dict instead of returning default
    current = data
    parts = path.split(".")
    for part in parts:
        if part in current:
            current = current[part]
        else:
            return self.get_nested_path(data, *keys, default=default)
    return current
