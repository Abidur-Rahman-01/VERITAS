"""CSV Dialect Sniffer."""

import re

def detect_delimiter(sample: str) -> str:
    """Detect delimiter among [',', '\t', ';']."""
    delimiters = [",", "\t", ";"]
    # Remove quoted sections before counting
    no_quotes = re.sub(r'"[^"]*"', '', sample)
    counts = {d: no_quotes.count(d) for d in delimiters}
    return max(counts, key=counts.get)
