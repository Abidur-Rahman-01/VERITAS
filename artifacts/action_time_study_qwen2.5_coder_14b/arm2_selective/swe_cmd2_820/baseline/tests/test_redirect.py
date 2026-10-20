from cmd2.redirect import parse_redirect

def test_simple_out():
    assert parse_redirect('build.sh > out.log')['stdout'] == 'out.log'

def test_combine_stderr():
    res = parse_redirect('build.sh > out.log 2>&1')
    assert res['stdout'] == 'out.log'
    assert res['combine_stderr'] is True
