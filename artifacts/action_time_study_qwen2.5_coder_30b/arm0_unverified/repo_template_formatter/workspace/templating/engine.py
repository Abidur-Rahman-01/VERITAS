"""Template Engine."""
import re

def render_template(template: str, context: dict) -> str:
    # FIXED: Use .get() to default to empty string for missing keys
    def replacer(match):
        key = match.group(1).strip()
        return str(context.get(key, ""))
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", replacer, template)
