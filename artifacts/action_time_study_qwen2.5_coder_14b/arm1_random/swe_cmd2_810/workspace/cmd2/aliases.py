"""Alias manager."""

def resolve_alias(alias_map: dict[str, str], name: str) -> str:
    # BUG: Only does 1-hop lookup instead of following chained aliases
    resolved = set()
while name in alias_map:
    if name in resolved:
        raise ValueError('Alias loop detected')
    resolved.add(name)
    name = alias_map[name]
return name
