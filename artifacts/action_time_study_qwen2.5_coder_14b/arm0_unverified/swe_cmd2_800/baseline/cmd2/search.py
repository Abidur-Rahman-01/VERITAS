"""History reverse search."""
import re

def find_last_matching_command(history: list[str], regex: str) -> str | None:
    # BUG: Searches forward instead of backward, returning earliest match instead of last
    for cmd in history:
        if re.search(regex, cmd):
            return cmd
    return None
