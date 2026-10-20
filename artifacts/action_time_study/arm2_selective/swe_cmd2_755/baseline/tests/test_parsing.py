import pytest
from cmd2.parsing import parse_command_line

def test_simple_redirect():
    cmd, redir = parse_command_line('echo hello > out.txt')
    assert cmd == 'echo hello'
    assert redir == 'out.txt'

def test_quoted_redirect_not_split():
    cmd, redir = parse_command_line('echo "hello > world"')
    assert cmd == 'echo "hello > world"'
    assert redir is None
