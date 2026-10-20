"""Alias manager."""

def resolve_alias(alias_map: dict[str, str], name: str) -> str:
    """Resolve an alias iteratively until no further alias expansion exists."""
    visited = set()
    while name in alias_map and name not in visited:
        visited.add(name)
        name = alias_map[name]
    return name
