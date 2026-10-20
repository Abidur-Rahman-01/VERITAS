from mdtable.table import format_row

def test_row():
    assert format_row(['A', 'B']) == '| A | B |'
