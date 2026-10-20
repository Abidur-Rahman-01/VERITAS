"""Command line framework."""
import os

class Cmd:
    def __init__(self, history_file='history.txt'):
        self.history_file = history_file

    def _read_history(self):
        if not os.path.exists(self.history_file):
            return []
        with open(self.history_file, 'r', encoding='utf-8') as f:
            return [l.strip() for l in f.readlines()]

    def _write_history(self, lines):
        # BUG: Crashes if directory does not exist
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, 'w', encoding='utf-8') as f:
            for l in lines:
                f.write(l + '\n')
