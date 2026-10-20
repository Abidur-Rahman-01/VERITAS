from cmd2.search import find_last_matching_command

def test_find_last_match():
    h = ['git status', 'ls -l', 'git commit -m first', 'pwd', 'git commit -m second']
    assert find_last_matching_command(h, r'git commit') == 'git commit -m second'
