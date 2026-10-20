"""ANSI terminal styling."""
import os

def colorize(text: str, color_code: str = '32') -> str:
    # Check if NO_COLOR is set and non-empty
    if os.environ.get('NO_COLOR'):
        return text
    return f'\033[{color_code}m{text}\033[0m'
