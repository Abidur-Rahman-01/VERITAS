"""Markdown Link Extractor."""
import re

def extract_links(text: str) -> list:
    # FIXED: Exclude image tags ![alt](url) by requiring negation of preceding '!'
    pattern = r"(?<!\!)\[([^\]]+)\]\(([^\)]+)\)"
    return [(m.group(1), m.group(2)) for m in re.finditer(pattern, text)]
