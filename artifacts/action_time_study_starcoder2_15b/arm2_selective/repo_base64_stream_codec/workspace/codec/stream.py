"""Stream base64 codec."""
import base64

def encode_chunks(chunks: list[bytes]) -> str:
    # BUG: Encodes each chunk separately producing broken concatenated padding
    return ''.join(base64.b64encode(c).decode() for c in chunks)
