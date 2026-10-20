"""Type Coercion."""

def coerce_value(val, target_type: str):
    """Coerce string/primitive val to target_type ('int', 'float', 'bool', 'str')."""
    if val is None:
        return None
    if target_type == "str":
        return str(val)
    if target_type == "int":
        return int(val)
    if target_type == "float":
        return float(val)
    if target_type == "bool":
        # BUG: Direct bool(val) evaluates non-empty strings like 'false', '0', 'no' as True
        return val.lower() in {'true', '1', 'yes', 't', 'y', '1.0'}
    raise ValueError(f"Unknown target type: {target_type}")
