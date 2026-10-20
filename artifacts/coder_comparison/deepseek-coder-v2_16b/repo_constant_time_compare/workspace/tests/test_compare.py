from cryptokit.compare import secure_compare

def test_identical_match():
    assert secure_compare("SecretToken123", "SecretToken123") is True

def test_case_sensitivity():
    assert secure_compare("SecretToken", "secrettoken") is False

def test_whitespace_sensitivity():
    assert secure_compare("Token ", "Token") is False
    assert secure_compare(" Token", "Token") is False

def test_non_string():
    assert secure_compare(None, "Token") is False
