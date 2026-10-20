from cmd2.prompt import format_prompt

def test_simple_prompt():
    assert format_prompt('{user}> ', 'admin') == 'admin> '

def test_escaped_braces():
    assert format_prompt('{{{user}}}', 'root') == '{root}'
