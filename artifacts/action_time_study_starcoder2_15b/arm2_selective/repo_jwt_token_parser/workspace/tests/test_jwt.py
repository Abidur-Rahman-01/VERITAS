import base64, json
from jwtsimple.jwt import parse_jwt_payload

def test_unpadded_payload():
    # JSON: {'sub': '123'}
    token = 'header.eyJzdWIiOiIxMjMifQ.sig'
    assert parse_jwt_payload(token) == {'sub': '123'}
