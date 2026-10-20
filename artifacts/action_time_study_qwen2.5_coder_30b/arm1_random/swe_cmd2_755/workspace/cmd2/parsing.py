"""Command line parser."""

def parse_command_line(cmd: str) -> tuple[str, str | None]:
    # Find the last '>' that is not inside quotes
    if '>' in cmd:
        # Split from the right to find the last '>' not inside quotes
        parts = cmd.rsplit('>', 1)
        # Check if the part after '>' is inside quotes
        before_redirect = parts[0]
        after_redirect = parts[1]
        
        # If there are quotes in the part before redirect, we need to check
        # if the last '>' is inside quotes
        if '"' in before_redirect or "'" in before_redirect:
            # Count quotes to determine if the last '>' is inside quotes
            quote_count = 0
            in_single_quote = False
            in_double_quote = False
            
            for i, char in enumerate(before_redirect):
                if char == '"' and not in_single_quote:
                    in_double_quote = not in_double_quote
                elif char == "'" and not in_double_quote:
                    in_single_quote = not in_single_quote
                
            # If we're still inside a quote, the redirect is inside quotes
            if in_single_quote or in_double_quote:
                return cmd.strip(), None
        
        return before_redirect.strip(), after_redirect.strip()
    return cmd.strip(), None
