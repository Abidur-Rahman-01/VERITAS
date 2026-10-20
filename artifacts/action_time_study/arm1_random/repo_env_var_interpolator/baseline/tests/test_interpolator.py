from configkit.interpolator import interpolate_env

def test_basic_interpolation():
    assert interpolate_env("http://${HOST}:${PORT}", {"HOST": "localhost", "PORT": "8080"}) == "http://localhost:8080"

def test_default_fallback_when_unset():
    assert interpolate_env("DB: ${DB_NAME:-app_dev}", {}) == "DB: app_dev"

def test_default_fallback_when_empty():
    assert interpolate_env("MODE=${MODE:-production}", {"MODE": ""}) == "MODE=production"

def test_missing_var_without_default():
    assert interpolate_env("Hello ${NAME}!", {}) == "Hello !"
