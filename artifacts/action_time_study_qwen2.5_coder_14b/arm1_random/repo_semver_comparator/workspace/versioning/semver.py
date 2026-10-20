"""Semantic Versioning."""

def compare_versions(v1: str, v2: str) -> int:
    """Return -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2."""
    # BUG: Lexicographical string comparison causes '1.10.0' < '1.9.0'
    v1_parts = list(map(int, v1.split('.')))
    v2_parts = list(map(int, v2.split('.')))
    for part1, part2 in zip(v1_parts, v2_parts):
        if part1 < part2:
            return -1
        elif part1 > part2:
            return 1
    if len(v1_parts) < len(v2_parts):
        return -1
    elif len(v1_parts) > len(v2_parts):
        return 1
    return 0
