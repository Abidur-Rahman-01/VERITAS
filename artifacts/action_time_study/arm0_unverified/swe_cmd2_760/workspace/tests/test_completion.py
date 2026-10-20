import pytest
from cmd2.completion import complete_subcommand

def test_prefix_matching():
    assert complete_subcommand(['start', 'stop', 'status'], 'st') == ['start', 'stop', 'status']
    assert complete_subcommand(['start', 'stop', 'status'], 'sto') == ['stop']

def test_empty_text_all_candidates():
    assert complete_subcommand(['start', 'stop'], '') == ['start', 'stop']
