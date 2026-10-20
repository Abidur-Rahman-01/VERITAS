"""CSV Dialect Sniffer."""

def detect_delimiter(sample: str) -> str:
    """Detect delimiter among [',', '\t', ';']."""
    delimiters = [",", "\t", ";"]
    # BUG: Naive character counting includes delimiters inside quoted strings
    sample_no_quotes = re.sub(r'"[^"]*"', '', sample)
    counts = {d: sample_no_quotes.count(d) for d in delimiters}
    return max(counts, key=counts.get)
