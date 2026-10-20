"""Stream base64 codec."""
import base64

def encode_chunks(chunks: list[bytes]) -> str:
    # FIX: Concatenate all chunks before encoding to avoid broken padding
    return base64.b64encode(b''.join(chunks)).decode()
