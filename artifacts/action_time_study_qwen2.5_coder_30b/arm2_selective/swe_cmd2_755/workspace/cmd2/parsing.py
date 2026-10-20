"""Command line parser."""

def parse_command_line(cmd: str) -> tuple[str, str | None]:
    # Find the last '>' that is not inside quotes
    if '>' in cmd:
        # Split from the right to find the last '>' not inside quotes
        parts = cmd.rsplit('>', 1)
        # Check if the part after '>' is inside quotes
        cmd_part = parts[0]
        redir_part = parts[1]
        
        # If the command part contains unmatched quotes, we need to be more careful
        # Count quotes to determine if '>' is inside quotes
        quote_count = 0
        in_single_quotes = False
        in_double_quotes = False
        
        # Find the last '>' not inside quotes by scanning backwards
        last_greater_index = -1
        for i in range(len(cmd) - 1, -1, -1):
            if cmd[i] == '"':
                if not in_single_quotes:
                    in_double_quotes = not in_double_quotes
            elif cmd[i] == "'":
                if not in_double_quotes:
                    in_single_quotes = not in_single_quotes
            elif cmd[i] == '>' and not in_single_quotes and not in_double_quotes:
                last_greater_index = i
                break
        
        if last_greater_index != -1:
            return cmd[:last_greater_index].strip(), redir_part.strip()
    return cmd.strip(), None
