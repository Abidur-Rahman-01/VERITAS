"""CSV delimiter and field validator."""

import csv
from io import StringIO

def split_csv_line(line: str, delimiter: str = ',') -> list[str]:
    if not line.strip():
        return []
    
    # Use csv.reader to properly handle quoted fields with embedded delimiters
    reader = csv.reader(StringIO(line), delimiter=delimiter, quotechar='"', quoting=csv.QUOTE_MINIMAL)
    result = next(reader)
    # Restore quotes in the output as they were in the original input
    return [field.strip('"') if field.startswith('"') and field.endswith('"') else field for field in result]
