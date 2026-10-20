"""Template Engine."""
import re

def render_template(template: str, context: dict) -> str:
    # BUG: Direct dictionary indexing raises KeyError on missing keys instead of returning empty string
    def replacer(match):
        key = match.group(1).strip()
        return str(context[key])
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", replacer, template)
