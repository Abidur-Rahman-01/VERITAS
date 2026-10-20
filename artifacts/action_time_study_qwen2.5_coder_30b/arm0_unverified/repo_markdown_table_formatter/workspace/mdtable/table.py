"""Markdown table formatter."""

def format_row(cells: list[str]) -> str:
    return f'| {" | ".join(cells)} |'
