"""CSV delimiter and field validator."""

def split_csv_line(line: str, delimiter: str = ',') -> list[str]:
    # BUG: Naive split fails on quoted fields with embedded delimiters
    return line.strip().split(delimiter)
