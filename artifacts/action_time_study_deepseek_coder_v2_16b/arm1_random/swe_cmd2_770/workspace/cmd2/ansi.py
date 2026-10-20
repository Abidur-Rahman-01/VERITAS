"""ANSI terminal styling."""
import os

import os

def colorize(text: str, color_code: str = '32') -> str:
    no_color = os.environ.get('NO_COLOR')
    if no_color and no_color != '':
        return text
    else:
        return f'\033[{color_code}m{text}\033[0m'
    # BUG: Does not inspect os.environ.get('NO_COLOR')
    return f'\033[{color_code}m{text}\033[0m'
