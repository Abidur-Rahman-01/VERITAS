"""Environment Variable Interpolator."""
import os
import re

def interpolate_env(template: str, env: dict = None) -> str:
    """Interpolate ${VAR} and ${VAR:-default} into template."""
    if env is None:
        env = dict(os.environ)

    def replace_var(match):
        expr = match.group(1).strip()
        if ":-" in expr:
            var_name, default_val = expr.split(":-", 1)
        else:
            var_name, default_val = expr, ""

        # BUG: Crashes with KeyError on missing variable when no default is given,
        # instead of expanding to empty string. Also ignores default when env val is empty string.
        if var_name in env:
            val = env[var_name]
            if val == "" and ":-" in expr:
                return default_val
            return str(val)
        elif ":-" in expr:
            return default_val
        else:
            return ""

    return re.sub(r"\$\{([^}]+)\}", replace_var, template)
