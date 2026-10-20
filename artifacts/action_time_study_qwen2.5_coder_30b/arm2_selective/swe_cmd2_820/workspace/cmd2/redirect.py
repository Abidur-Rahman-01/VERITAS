"""Redirection handler."""

def parse_redirect(command_line: str) -> dict:
    # Handle '2>&1' redirection
    if '2>&1' in command_line:
        cmd, out = command_line.split('2>&1', 1)
        # Strip the stdout file path from the command part
        if '>' in cmd:
            cmd_part, _ = cmd.rsplit('>', 1)
            return {'command': cmd_part.strip(), 'stdout': out.strip(), 'combine_stderr': True}
        else:
            return {'command': cmd.strip(), 'stdout': out.strip(), 'combine_stderr': True}
    elif '>' in command_line:
        cmd, out = command_line.split('>', 1)
        return {'command': cmd.strip(), 'stdout': out.strip(), 'combine_stderr': False}
    return {'command': command_line.strip(), 'stdout': None, 'combine_stderr': False}
