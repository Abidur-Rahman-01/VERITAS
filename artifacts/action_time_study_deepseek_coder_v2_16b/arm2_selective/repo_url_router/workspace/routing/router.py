"""URL Path Pattern Matcher."""
import re

def match_route(pattern: str, path: str):
    """Match URL route pattern (e.g. '/users/<int:id>/posts/<slug>') against path."""
    # BUG: Does not anchor regex with ^ and $, allowing partial matches,
    # and does not cast typed parameters like <int:name> to integers.
    regex_pattern = re.compile(r"^" + re.sub(r"<int:(\w+)>", r"(?P<\1>\d+)", pattern) + r"$")
    regex_pattern = re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", regex_pattern)

    match = re.search(regex_pattern, path)
    if not match:
        return None
    return match.groupdict()
