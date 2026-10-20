"""Cron matcher."""

def matches_minute(field: str, current_minute: int) -> bool:
    # BUG: Fails on step expressions like '*/15'
    if field == '*':
        return True
    return field == str(current_minute)
