"""Comment filter."""

def strip_comments(lines: list[str]) -> list[str]:
    # Only strip lines that start with '#' (ignoring leading whitespace)
    return [l for l in lines if not l.lstrip().startswith('#')]
