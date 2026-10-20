"""Command line short flag parser."""

def parse_flags(argv: list[str]) -> dict[str, bool]:
    flags = {}
    for arg in argv:
        if arg.startswith('-') and not arg.startswith('--'):
            # Handle combined short flags like -xvf
            for flag in arg[1:]:
                flags[flag] = True
    return flags
