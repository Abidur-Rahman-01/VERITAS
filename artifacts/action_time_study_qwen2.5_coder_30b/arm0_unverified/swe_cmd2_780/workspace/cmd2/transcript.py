"""Transcript recording session."""

class Transcript:
    def __init__(self):
        self.history = []
        self.active_buffer = []

    def record(self, cmd: str):
        self.history.append(cmd)

    def abort(self):
        # FIX: Only clear active_buffer, preserve history
        self.active_buffer.clear()
