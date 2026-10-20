"""Command line parser."""

def parse_command_line(cmd: str) -> tuple[str, str | None]:
    # BUG: Naive split on '>' splits redirect symbols inside quotes
    if '>' in cmd:
        parts = cmd.split('>', 1)
        return parts[0].strip(), parts[1].strip()
    return cmd.strip(), None
