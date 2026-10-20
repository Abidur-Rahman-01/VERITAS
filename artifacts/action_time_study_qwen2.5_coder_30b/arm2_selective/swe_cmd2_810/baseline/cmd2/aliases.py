"""Alias manager."""

def resolve_alias(alias_map: dict[str, str], name: str) -> str:
    # BUG: Only does 1-hop lookup instead of following chained aliases
    return alias_map.get(name, name)
