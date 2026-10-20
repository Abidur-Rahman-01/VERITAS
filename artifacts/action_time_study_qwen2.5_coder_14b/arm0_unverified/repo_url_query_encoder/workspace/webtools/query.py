"""Query Parameter Encoder."""
import urllib.parse

def encode_query_params(params: dict) -> str:
    pairs = []
    for k, v in params.items():
        # BUG: Converts list directly to string representation instead of expanding into multiple key-value pairs
        if isinstance(v, (list, tuple)):
            pairs.extend((k, urllib.parse.quote_plus(str(item))) for item in v)
        else:
            pairs.append((k, urllib.parse.quote_plus(str(v), safe=' ')))
        if not params:
            return ""
    return "&".join(f"{urllib.parse.quote_plus(str(k))}={urllib.parse.quote_plus(str(v))}" for k, v in pairs)
