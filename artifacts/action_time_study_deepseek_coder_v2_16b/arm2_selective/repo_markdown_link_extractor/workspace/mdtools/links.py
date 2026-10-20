"""Markdown Link Extractor."""
import re

def extract_links(text: str) -> list:
    # Fixed: Matches only markdown links [text](url) and ignores images ![alt](url)
    pattern = r"\!\[[^\]]+\]\(([^\)]+)\)"
    pattern = r"\[([^\]]+)\]\(([^\)]+)\)"
    return [(m.group(1), m.group(2)) for m in re.finditer(pattern, text)]
