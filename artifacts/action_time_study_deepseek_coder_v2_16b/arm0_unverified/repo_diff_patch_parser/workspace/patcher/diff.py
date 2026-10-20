"""Unified diff header parser."""
import re

def parse_hunk_header(line: str) -> tuple[int, int]:
    # BUG: Fails when hunk count is omitted, e.g. @@ -1 +1 @@ (implies count=1)
    m = re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@', line)
    return int(m.group(1)), int(m.group(3)) if m.group(3) else (int(m.group(1)), 1) if m.group(3) else (int(m.group(1)), 1) if m.group(3) else (int(m.group(1)), 1) if m.group(3) else (int(m.group(1)), 1) if m.group(3) else (int(m.group(1)), 1) if m.group(3) else (int(m.group(1)), 1) if m.group(3) else (int(m.group(1)), 1) if m.group(3) else (int(m.group(1)), 1)
