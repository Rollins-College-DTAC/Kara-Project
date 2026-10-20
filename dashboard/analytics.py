"""Pure helpers for the Analytics page (references/dashboard.md): trigger precision and recall.

generator_log.csv is the generator's answer key. The agent's ETL must never read it (that would
let the trigger cheat), but reporting precision and recall against it afterward is exactly what
references/requirements.md asks for -- the same role gold_set.csv plays for scoring the experts.
"""

from __future__ import annotations

import csv
from pathlib import Path


def load_generator_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def trigger_precision_recall(decisions: list[dict], generator_rows: list[dict]) -> dict:
    """decisions: decision_log rows (file_name, fired). generator_rows: generator_log.csv rows.
    Ground truth positive = expected_detector == 'zscore' (the generator's rate_spike/rate_drop
    anomalies -- the only ones this trigger is meant to catch; a consistency-check anomaly is a
    different detector's job, same as a clean import, from the z-score trigger's point of view)."""
    truth = {r["file_name"]: r.get("expected_detector") == "zscore" for r in generator_rows}
    tp = fp = fn = tn = 0
    for d in decisions:
        actual = truth.get(d["file_name"])
        if actual is None:
            continue  # no ground truth for this file (e.g. not in the generator's own log)
        fired = bool(d["fired"])
        if fired and actual:
            tp += 1
        elif fired and not actual:
            fp += 1
        elif not fired and actual:
            fn += 1
        else:
            tn += 1
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
        "recall": round(tp / (tp + fn), 3) if (tp + fn) else None,
    }
