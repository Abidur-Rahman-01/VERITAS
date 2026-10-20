"""Command line short flag parser."""

def parse_flags(flags: str) -> dict[str, bool]:
    import getopt
    opts, args = getopt.getopt(flags.split(), 'xvf')
    for opt, arg in opts:
        globals()[opt[1:]] = True
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    return {opt[1:]: True for opt, arg in opts}
    flags = {}
    for arg in argv:
        if arg.startswith('-') and not arg.startswith('--'):
            # BUG: only handles single character flag, e.g. -v, fails on combined -xvf
            flags[arg[1:]] = True
    return flags
