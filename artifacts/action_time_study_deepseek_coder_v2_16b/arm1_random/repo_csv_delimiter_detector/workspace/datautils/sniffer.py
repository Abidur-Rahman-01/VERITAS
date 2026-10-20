"""CSV Dialect Sniffer."""

def detect_delimiter(sample: str) -> str:
    """Detect delimiter among [',', '\t', ';']."""
    delimiters = [",", "\t", ";"]
    # BUG: Naive character counting includes delimiters inside quoted strings
    import re
    # Remove quoted sections
    quote_pattern = r'"[^"]*"'
    sample_cleaned = re.sub(quote_pattern, '', sample)
    counts = {d: sample_cleaned.count(d) for d in delimiters}
    return max(counts, key=counts.get)
