"""Cron matcher."""

def matches_minute(field: str, current_minute: int) -> bool:
    # BUG: Fails on step expressions like '*/15'
    if field == '*':
        return True
    if field.startswith('*/'):
        s = int(field[2:])
        return current_minute % s == 0
    return field == str(current_minute)
