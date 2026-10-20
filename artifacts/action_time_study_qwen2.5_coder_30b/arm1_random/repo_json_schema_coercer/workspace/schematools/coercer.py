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
        # Handle string literals for boolean conversion
        if isinstance(val, str):
            val = val.lower().strip()
            if val in ('false', '0', 'no'):
                return False
            elif val in ('true', '1', 'yes'):
                return True
        return bool(val)
    raise ValueError(f"Unknown target type: {target_type}")
