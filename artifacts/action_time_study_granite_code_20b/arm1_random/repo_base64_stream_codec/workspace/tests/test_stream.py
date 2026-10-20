import base64
from codec.stream import encode_chunks

def test_stream_matches_full():
    raw = b'hello world from python'
    chunks = [raw[:5], raw[5:]]
    assert encode_chunks(chunks) == base64.b64encode(raw).decode()
