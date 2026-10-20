"""Command line short flag parser."""

def parse_flags(argv: list[str]) -> dict[str, bool]:
    flags = {}
    for arg in argv:
        if arg.startswith('-') and not arg.startswith('--'):
            # BUG: only handles single character flag, e.g. -v, fails on combined -xvf
            flags[arg[1:]] = True
    return flags
