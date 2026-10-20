"""Comment filter."""

def strip_comments(lines: list[str]) -> list[str]:
    # BUG: Strips lines containing '#' anywhere, even inside strings
    return [l for l in lines if '#' not in l]
