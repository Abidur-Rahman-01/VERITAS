"""ISO 8601 Duration Parser."""
import re

def parse_iso_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration string into total seconds."""
    # BUG: Requires both Days and Time parts (P...DT...), crashing when only time (PT...) or only days (P...D) is provided
    pattern = r"^P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$"
    match = re.match(pattern, duration_str)
    if not match:
        raise ValueError(f"Invalid duration format: {duration_str}")
    days = int(match.group(1))
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds
