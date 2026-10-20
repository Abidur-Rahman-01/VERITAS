from cmd2.aliases import resolve_alias

def test_single_hop():
    assert resolve_alias({'g': 'git'}, 'g') == 'git'

def test_chained_alias():
    # Multi-hop: 'g' -> 'git' -> '/usr/bin/git'
    assert resolve_alias({'g': 'git', 'git': '/usr/bin/git'}, 'g') == '/usr/bin/git'
