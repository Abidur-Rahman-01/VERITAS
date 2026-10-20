from patcher.diff import parse_hunk_header

def test_full_header():
    assert parse_hunk_header('@@ -10,5 +20,6 @@') == (10, 20)

def test_single_line_header():
    assert parse_hunk_header('@@ -1 +1 @@') == (1, 1)
