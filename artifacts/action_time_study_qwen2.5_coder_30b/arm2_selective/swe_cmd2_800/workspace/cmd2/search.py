"""History reverse search."""
import re

def find_last_matching_command(history: list[str], regex: str) -> str | None:
    # Search backward through history to return the most recent matching command
    for cmd in reversed(history):
        if re.search(regex, cmd):
            return cmd
    return None
