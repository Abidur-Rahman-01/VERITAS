"""ANSI terminal styling."""
import os

def colorize(text: str, color_code: str = '32') -> str:
    # BUG: Does not inspect os.environ.get('NO_COLOR')
    return f'\033[{color_code}m{text}\033[0m'
