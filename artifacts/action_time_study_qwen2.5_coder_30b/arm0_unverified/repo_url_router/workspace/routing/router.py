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
    # Find all <int:...> patterns in the original pattern
    int_matches = re.findall(r"<int:(\w+)>", pattern)
    for param_name in int_matches:
        if param_name in result:
            result[param_name] = int(result[param_name])
    
    return result
