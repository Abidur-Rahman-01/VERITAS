"""Transcript recording session."""

class Transcript:
    def __init__(self):
        self.history = []
        self.active_buffer = []

    def record(self, cmd: str):
        self.history.append(cmd)

    def abort(self):
    self.active_buffer = ''
    self.history = self.history
        # BUG: Clears history along with active_buffer
        self.history.clear()
        self.active_buffer.clear()
