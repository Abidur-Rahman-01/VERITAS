"""HTTP Header Normalizer."""

def normalize_headers(raw_headers: list) -> dict:
    """Normalize headers: lowercase keys, strip whitespace, and combine duplicate keys with comma."""
    normalized = {}
    for key, val in raw_headers:
        k = key.lower().strip()
        v = str(val).strip()
        # BUG: Overwrites duplicate headers instead of combining with ', '
        normalized[k] = v
    return normalized
