import os
import pytest
from cmd2.cmd2 import Cmd

def test_history_in_nested_dir(tmp_path):
    nested = tmp_path / 'nonexistent' / 'nested' / 'hist.txt'
    cmd = Cmd(history_file=str(nested))
    cmd._write_history(['hello', 'world'])
    assert nested.exists()
    assert cmd._read_history() == ['hello', 'world']
