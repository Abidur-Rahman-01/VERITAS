"""Alias manager."""

def resolve_alias(alias_map: dict[str, str], name: str) -> str:
    # BUG: Only does 1-hop lookup instead of following chained aliases
    while name in alias_map:
        name = alias_map[name]
    return name
