import pytest
from cli_engine.parser import parse_flags

def test_single_flag():
    assert parse_flags(['-v']) == {'v': True}

def test_combined_flags():
    assert parse_flags(['-xvf']) == {'x': True, 'v': True, 'f': True}

def test_multiple_args():
    assert parse_flags(['-a', '-bc']) == {'a': True, 'b': True, 'c': True}
