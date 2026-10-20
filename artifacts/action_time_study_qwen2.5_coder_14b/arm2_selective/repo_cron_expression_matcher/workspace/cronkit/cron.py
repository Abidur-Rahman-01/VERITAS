"""Cron matcher."""

def matches_minute(field: str, current_minute: int) -> bool:
    # BUG: Fails on step expressions like '*/15'
    if field.startswith('*/'):
        step = int(field[2:])
        return current_minute % step == 0
    elif field == '*':
        return True
    return field == str(current_minute)
