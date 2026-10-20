"""Subcommand completion."""

def complete_subcommand(subcommands: list[str], text: str) -> list[str]:
    # BUG: Returns empty list when text is empty instead of returning all subcommands
    if not text:
        return []
    return [s for s in subcommands if s.startswith(text)]
