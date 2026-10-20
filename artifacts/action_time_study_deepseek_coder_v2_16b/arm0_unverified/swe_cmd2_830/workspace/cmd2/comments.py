"""Comment filter."""

def strip_comments(lines: list[str]) -> list[str]:
    stripped_lines = []
    for line in lines:
        stripped_line = line.lstrip()
        if stripped_line and not stripped_line.startswith('#'):
            stripped_lines.append(line)
    return stripped_lines
    # BUG: Strips lines containing '#' anywhere, even inside strings
    return [l for l in lines if '#' not in l]
