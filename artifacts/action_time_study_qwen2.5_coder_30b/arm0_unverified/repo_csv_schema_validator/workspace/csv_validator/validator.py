"""CSV delimiter and field validator."""

import csv
from io import StringIO

def split_csv_line(line: str, delimiter: str = ',') -> list[str]:
    # Use csv module to properly handle quoted fields with embedded delimiters
    if not line.strip():
        return []
    reader = csv.reader(StringIO(line), delimiter=delimiter, quotechar='"', quoting=csv.QUOTE_MINIMAL)
    result = next(reader)
    return result
