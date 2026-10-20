"""URL Path Pattern Matcher."""
import re

def match_route(pattern: str, path: str):
    """Match URL route pattern (e.g. '/users/<int:id>/posts/<slug>') against path."""
    # Anchor regex with ^ and $ to match entire path
    regex_pattern = re.sub(r"<int:(\w+)>", r"(?P<\1>\\d+)", pattern)
    regex_pattern = re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", regex_pattern)
    regex_pattern = f"^{regex_pattern}$"

    match = re.search(regex_pattern, path)
    if not match:
        return None
    
    # Cast <int:...> matched parameters to Python int values
    result = match.groupdict()
    # Pre-compile the pattern for efficiency
    int_pattern = re.compile(r"<int:(\w+)>")
    for key, value in result.items():
        # Check if the original pattern had <int:...> for this group
        if int_pattern.search(pattern):
            try:
                result[key] = int(value)
            except ValueError:
                return None
    return result
