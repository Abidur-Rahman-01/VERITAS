"""Redirection handler."""

def parse_redirect(command_line: str) -> dict:
    # BUG: Fails to detect '2>&1' and only detects '>'
    if '>' in command_line or '2>&1' in command_line:
        cmd, out = command_line.split('>', 1)
        if '2>&1' in command_line:
            cmd, _ = command_line.split('2>&1', 1)
            return {'command': cmd.strip(), 'stdout': None, 'combine_stderr': True}
        elif '>' in command_line:
            cmd, out = command_line.split('>', 1)
            return {'command': cmd.strip(), 'stdout': out.strip(), 'combine_stderr': False}
        else:
            return {'command': command_line.strip(), 'stdout': None, 'combine_stderr': False}
    return {'command': command_line.strip(), 'stdout': None, 'combine_stderr': False}
