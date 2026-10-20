"""CSV Dialect Sniffer."""

def detect_delimiter(sample: str) -> str:
    """Detect delimiter among [',', '\t', ';']."""
    delimiters = [",", "\t", ";"]
    # BUG: Naive character counting includes delimiters inside quoted strings
    import re
    clean_sample = re.sub(r'"[^"]*"', '', sample)
    counts = {d: clean_sample.count(d) for d in delimiters}
    return max(counts, key=counts.get)
