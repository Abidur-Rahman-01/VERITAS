"""HTTP Header Normalizer."""

def normalize_headers(raw_headers: list) -> dict:
    """Normalize headers: lowercase keys, strip whitespace, and combine duplicate keys with comma."""
    normalized = {}
    for key, val in raw_headers:
        k = key.lower().strip()
        v = str(val).strip()
        if k in normalized:
            normalized[k] += ", " + v
        else:
            normalized[k] = v
    return normalized
