"""CSV delimiter and field validator."""

def split_csv_line(line: str, delimiter: str = ',') -> list[str]:
    # BUG: Naive split fails on quoted fields with embedded delimiters
    import csv
from io import StringIO

def split_csv_line(line: str, delimiter: str = ',') -> list[str]:
    # Use csv module to handle quoted fields with embedded delimiters
    reader = csv.reader(StringIO(line), delimiter=delimiter)
    return next(reader)
