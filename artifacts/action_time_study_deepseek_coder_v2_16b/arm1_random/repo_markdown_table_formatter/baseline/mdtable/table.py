"""Markdown table formatter."""

def format_row(cells: list[str]) -> str:
    # BUG: Does not enclose row in '| ' and ' |'
    return ' | '.join(cells)
