"""Pure helpers for the Data page's data-quality metrics (references/dashboard.md).
No Streamlit import, so these are testable without running the app.
"""

from __future__ import annotations

import json


def flag_counts(silver_rows: list[dict]) -> dict[str, int]:
    """How many records broke each consistency rule. A record can break more than one
    rule, so this counts rule occurrences, not records."""
    counts: dict[str, int] = {}
    for row in silver_rows:
        if row["consistency_ok"]:
            continue
        for flag in json.loads(row["consistency_flags"] or "[]"):
            counts[flag] = counts.get(flag, 0) + 1
    return counts


def status_breakdown(silver_rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in silver_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return counts
