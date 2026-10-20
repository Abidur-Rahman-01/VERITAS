"""JWT parser."""
import base64, json

def parse_jwt_payload(token: str) -> dict:
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    payload_b64 = token.split('.')[1]
    # add '=' * (-len(payload_b64) % 4) before decoding so unpadded base64 strings decode cleanly
    payload_b64 += '=' * (-len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))
    parts = token.split('.')
    # BUG: Fails on missing base64 padding without adding '=' to length multiple of 4
    payload_b64 = parts[1]
    decoded = base64.urlsafe_b64decode(payload_b64)
    return json.loads(decoded)
