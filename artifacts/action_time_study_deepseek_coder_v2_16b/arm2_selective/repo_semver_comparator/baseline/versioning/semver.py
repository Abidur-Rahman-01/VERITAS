"""Semantic Versioning."""

def compare_versions(v1: str, v2: str) -> int:
    """Return -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2."""
    # BUG: Lexicographical string comparison causes '1.10.0' < '1.9.0'
    if v1 < v2:
        return -1
    elif v1 > v2:
        return 1
    return 0
