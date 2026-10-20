"""CSV delimiter and field validator."""

def split_csv_line(line: str, delimiter: str = ',') -> list[str]:
    # BUG: Naive split fails on quoted fields with embedded delimiters
    import csv
import io

def split_csv_line(line: str, delimiter: str = ',') -> list[str]:
    import csv
    import io
    def split_csv_line(line: str, delimiter: str = ',') -> list[str]:
        import csv
        import io
        reader = csv.reader(io.StringIO(line.strip()), delimiter=delimiter)
        return next(reader)
