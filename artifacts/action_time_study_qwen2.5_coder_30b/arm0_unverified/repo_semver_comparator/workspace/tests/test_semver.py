from versioning.semver import compare_versions

def test_equal_versions():
    assert compare_versions("1.0.0", "1.0.0") == 0

def test_major_minor_numeric_order():
    # '1.10.0' must be greater than '1.9.0'
    assert compare_versions("1.10.0", "1.9.0") == 1
    assert compare_versions("1.9.0", "1.10.0") == -1

def test_patch_order():
    assert compare_versions("2.0.1", "2.0.15") == -1
    assert compare_versions("2.0.15", "2.0.1") == 1
