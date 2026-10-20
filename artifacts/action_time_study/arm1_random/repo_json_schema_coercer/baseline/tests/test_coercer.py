from schematools.coercer import coerce_value

def test_coerce_int_and_float():
    assert coerce_value("42", "int") == 42
    assert coerce_value("3.14", "float") == 3.14

def test_coerce_bool_true():
    assert coerce_value("true", "bool") is True
    assert coerce_value("1", "bool") is True
    assert coerce_value("True", "bool") is True

def test_coerce_bool_false():
    assert coerce_value("false", "bool") is False
    assert coerce_value("0", "bool") is False
    assert coerce_value("False", "bool") is False
    assert coerce_value("no", "bool") is False
