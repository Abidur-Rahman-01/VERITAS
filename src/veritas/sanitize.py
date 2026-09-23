import re

from .io import digest

SECRETS = [
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        "[REDACTED KEY]",
    ),
    (
        re.compile(r"(?i)\b(api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*[^\s,;]+"),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b"),
        "[REDACTED TOKEN]",
    ),
    (re.compile(r"(?i)bearer\s+\S+"), "Bearer [REDACTED]"),
]
INJECTION = re.compile(
    r"(?im)^.*(?:ignore (?:all |the )?(?:previous|prior|system) instructions|"
    r"<\|(?:im_start|system)\|>|^\s*(?:system|developer)\s*:).*$"
)


def redact(text):
    for pattern, replacement in SECRETS:
        text = pattern.sub(replacement, text)
    return text


def sanitize(text, source, limit=16000):
    """Defense in depth, NOT a proof that arbitrary prompt injection is removed."""
    raw_hash = digest(text)
    cleaned, removed = INJECTION.subn("[QUARANTINED INSTRUCTION-LIKE LINE]", redact(text))
    return {
        "type": "untrusted_observation",
        "source": source,
        "sha256": raw_hash,
        "content": cleaned[:limit],
        "truncated": len(cleaned) > limit,
        "quarantined_lines": removed,
        "trusted_as_instructions": False,
    }
