"""Semantic Versioning."""

def compare_versions(v1: str, v2: str) -> int:
    """Return -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2."""
    # BUG: Lexicographical string comparison causes '1.10.0' < '1.9.0'
    parts1 = list(map(int, v1.split('.'))) 
    parts2 = list(map(int, v2.split('.'))) 
    for i in range(max(len(parts1), len(parts2))):
        num1 = parts1[i] if i < len(parts1) else 0
        num2 = parts2[i] if i < len(parts2) else 0
        if num1 < num2:
            return -1
        elif num1 > num2:
            return 1
    return 0
    return 0
