"""Markdown Link Extractor."""
import re

def extract_links(text: str) -> list:
    # BUG: Matches image tags ![alt](url) as regular links because it does not check for preceding '!'
    pattern = r"\[([^\]]+)\]\(([^\)]+)\)"
    return [(m.group(1), m.group(2)) for m in re.finditer(pattern, text)]
