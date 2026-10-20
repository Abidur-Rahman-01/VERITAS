import os
import pytest
from cmd2.ansi import colorize

def test_standard_colorize():
    assert colorize('ok', '32') == '\033[32mok\033[0m'

def test_no_color_environment(monkeypatch):
    monkeypatch.setenv('NO_COLOR', '1')
    assert colorize('ok', '32') == 'ok'
