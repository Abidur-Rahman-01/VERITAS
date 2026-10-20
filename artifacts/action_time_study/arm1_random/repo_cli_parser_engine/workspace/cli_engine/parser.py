"""Command line short flag parser."""

def parse_flags(argv: list[str]) -> dict[str, bool]:
    flags = {}
    for arg in argv:
        if arg.startswith('-') and not arg.startswith('--'):
            # BUG: only handles single character flag, e.g. -v, fails on combined -xvf
            for char in arg[1:]:
                flags[char] = True
    return flags
