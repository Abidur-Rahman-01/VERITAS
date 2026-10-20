"""Levenshtein distance."""

def levenshtein(s1: str, s2: str) -> int:
    # BUG: Returns difference in string lengths instead of edit distance
    return abs(len(s1) - len(s2))
