from cmd2.comments import strip_comments

def test_strip_full_line_comment():
    assert strip_comments(['# comment', 'run']) == ['run']

def test_preserve_inline_hash_in_quotes():
    assert strip_comments(['echo "#tag"']) == ['echo "#tag"']
