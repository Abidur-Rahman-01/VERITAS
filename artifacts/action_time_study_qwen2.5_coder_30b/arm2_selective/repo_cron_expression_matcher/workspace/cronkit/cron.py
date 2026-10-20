"""Cron matcher."""

def matches_minute(field: str, current_minute: int) -> bool:
    # Handle step expressions like '*/15'
    if field.startswith('*/'):
        s = int(field[2:])
        return current_minute % s == 0
    if field == '*':
        return True
    return field == str(current_minute)
