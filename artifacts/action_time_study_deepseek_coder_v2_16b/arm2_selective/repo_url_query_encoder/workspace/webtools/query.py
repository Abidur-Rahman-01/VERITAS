"""Query Parameter Encoder."""
import urllib.parse

def encode_query_params(params: dict) -> str:
    pairs = []
    for k, v in params.items():
        # BUG: Converts list directly to string representation instead of expanding into multiple key-value pairs
        if isinstance(v, (list, tuple)):
            for item in v:
                pairs.append((k, item))
        else:
            pairs.append((k, v))
    return "&".join(f"{urllib.parse.quote_plus(str(k))}={urllib.parse.quote_plus(str(v))}" for k, v in pairs)
