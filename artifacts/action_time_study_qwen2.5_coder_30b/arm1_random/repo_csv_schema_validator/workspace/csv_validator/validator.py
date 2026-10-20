"""CSV delimiter and field validator."""

import csv
from io import StringIO

def split_csv_line(line: str, delimiter: str = ',') -> list[str]:
    if not line.strip():
        return []
    
    # Use csv.reader to properly handle quoted fields with embedded delimiters
    reader = csv.reader(StringIO(line), delimiter=delimiter, quotechar='"', quoting=csv.QUOTE_MINIMAL)
    result = next(reader)
    
    # The csv module strips quotes by default. To preserve the original format,
    # we need to reconstruct fields that were originally quoted.
    # For simplicity and correctness, let's use a different approach:
    # parse with csv module but then reconstruct the original field representation
    
    # First, let's try a simpler approach - if we have quoted fields in input,
    # they should remain quoted in output. We'll check if the original line had quotes.
    
    # Parse using csv.reader to get correct field boundaries
    # Then reconstruct with original quoting preserved
    fields = []
    i = 0
    while i < len(line):
        if line[i] == '"':
            # Find the matching quote
            start = i
            i += 1
            while i < len(line) and line[i] != '"':
                i += 1
            if i < len(line):  # Found closing quote
                i += 1  # Skip the closing quote
                fields.append(line[start:i])
            else:
                # Unclosed quote - treat as regular field
                fields.append(line[start:])
                break
        elif line[i] == delimiter:
            fields.append('')
            i += 1
        else:
            start = i
            while i < len(line) and line[i] != delimiter and line[i] != '"':
                i += 1
            fields.append(line[start:i])
    
    # Filter out empty fields that were just delimiters
    result_fields = []
    field_start = 0
    for i in range(len(fields)):
        if fields[i] == '' and i > 0 and fields[i-1] != '':
            continue  # Skip empty fields that are just delimiters
        result_fields.append(fields[i])
    
    return result_fields
