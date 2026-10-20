"""JWT parser."""
import base64, json

def parse_jwt_payload(token: str) -> dict:
    parts = token.split('.')
    # BUG: Fails on missing base64 padding without adding '=' to length multiple of 4
    payload_b64 = parts[1]
    payload_b64 += '=' * (-len(payload_b64) % 4)
    decoded = base64.urlsafe_b64decode(payload_b64)
    return json.loads(decoded)
