"""Semantic Versioning."""

def compare_versions(v1: str, v2: str) -> int:
    """Return -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2."""
    # Parse version strings into components
    v1_components = [int(x) for x in v1.split('.')]
    v2_components = [int(x) for x in v2.split('.')]
    
    # Compare each component numerically
    for c1, c2 in zip(v1_components, v2_components):
        if c1 < c2:
            return -1
        elif c1 > c2:
            return 1
    
    # If all components are equal
    return 0
