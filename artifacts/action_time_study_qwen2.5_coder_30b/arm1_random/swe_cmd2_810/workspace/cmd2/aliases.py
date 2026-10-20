"""Alias manager."""

def resolve_alias(alias_map: dict[str, str], name: str) -> str:
    """Resolve an alias iteratively until no further alias expansion exists."""
    visited = set()
    current = name
    while current in alias_map and current not in visited:
        visited.add(current)
        current = alias_map[current]
    return current
