"""UUID validator."""
import re

def is_valid_uuid4(val: str) -> bool:
    # BUG: Allows arbitrary versions instead of enforcing version 4 (8-4-4-4-12 hex with '4' at pos 14)
    pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    return bool(re.match(pattern, val.lower()))
