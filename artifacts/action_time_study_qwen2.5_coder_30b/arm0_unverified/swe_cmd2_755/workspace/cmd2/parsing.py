"""Command line parser."""

def parse_command_line(cmd: str) -> tuple[str, str | None]:
    # Find the last unquoted '>' symbol
    if '>' in cmd:
        # Split from the right to find the last '>' not inside quotes
        parts = cmd.rsplit('>', 1)
        # Check if the part after '>' is inside quotes
        cmd_part = parts[0]
        # Count quotes to determine if '>' is inside quotes
        quote_count = 0
        in_single_quote = False
        in_double_quote = False
        
        for i, char in enumerate(cmd_part):
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            
        # If we're not inside quotes, split on the last '>'
        if not in_single_quote and not in_double_quote:
            return parts[0].strip(), parts[1].strip()
    return cmd.strip(), None
