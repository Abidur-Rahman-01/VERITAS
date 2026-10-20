import pytest
from cmd2.transcript import Transcript

def test_record_commands():
    t = Transcript()
    t.record('cmd 1')
    assert t.history == ['cmd 1']

def test_abort_preserves_committed_history():
    t = Transcript()
    t.record('cmd 1')
    t.active_buffer.append('partial')
    t.abort()
    assert t.history == ['cmd 1']
    assert t.active_buffer == []
