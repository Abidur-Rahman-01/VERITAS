"""Query Parameter Encoder."""
import urllib.parse

def encode_query_params(params: dict) -> str:
    if not params:
        return ""
    
    pairs = []
    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            # For list/tuple values, create multiple key-value pairs
            for item in v:
                pairs.append((k, item))
        else:
            pairs.append((k, v))
    
    return "&".join(f"{urllib.parse.quote_plus(str(k))}={urllib.parse.quote_plus(str(v))}" for k, v in pairs)
