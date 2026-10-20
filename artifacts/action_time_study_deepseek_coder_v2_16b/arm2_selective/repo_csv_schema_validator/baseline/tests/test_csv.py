import pytest
from csv_validator.validator import split_csv_line

def test_simple_split():
    assert split_csv_line('a,b,c') == ['a', 'b', 'c']

def test_quoted_split():
    assert split_csv_line('"a,b",c') == ['"a,b"', 'c']

def test_semicolon_split():
    assert split_csv_line('1;2;3', delimiter=';') == ['1', '2', '3']
