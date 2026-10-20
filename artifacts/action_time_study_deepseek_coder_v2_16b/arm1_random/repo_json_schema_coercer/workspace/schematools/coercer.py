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
        # FIX: Coerce specific string literals to bool
        if isinstance(val, str):
            lower_val = val.lower()
            if lower_val in ("false", "0", "no", "false"):
                return False
            elif lower_val in ("true", "1", "yes", "true"):
                return True
        return bool(val)
    raise ValueError(f"Unknown target type: {target_type}")
