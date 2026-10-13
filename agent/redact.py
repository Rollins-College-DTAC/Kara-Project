"""Step 3, Redact: mask anything that looks like personal data before any model call.

The data is fake, but the pipeline behaves as if it were real. The raw layer keeps the
original text; only the copy sent to models is masked.
"""

from __future__ import annotations

import re

MISSING = {"", "n/a", "na", "none", "null"}

# Order matters: the SSN pattern must run before the phone pattern.
PATTERNS = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("PHONE", re.compile(r"\(?\b\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")),
    ("ID_NUMBER", re.compile(r"\b(?:ID|id|Id)\s*[:#]?\s*\d{6,}\b")),
]


def note_text(value) -> str:
    """The notes field as a clean string; missing tokens like None, '' or 'N/A' become ''."""
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in MISSING else text


def redact(text: str) -> tuple[str, int]:
    """Return (masked text, number of masks applied)."""
    total = 0
    for label, pattern in PATTERNS:
        text, n = pattern.subn(f"[{label}]", text)
        total += n
    return text, total
