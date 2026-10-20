"""Pure helpers for the Pipeline History page (references/dashboard.md): step durations and
rows in/out per run. No Streamlit import, so these are testable without running the app.
"""

from __future__ import annotations

import statistics
from datetime import datetime


def duration_ms(row: dict) -> float | None:
    if not row.get("started_at") or not row.get("finished_at"):
        return None
    start = datetime.fromisoformat(row["started_at"])
    end = datetime.fromisoformat(row["finished_at"])
    return (end - start).total_seconds() * 1000


def step_duration_summary(run_log_rows: list[dict]) -> list[dict]:
    """Mean/median/max duration per step, across whatever runs were passed in."""
    by_step: dict[str, list[float]] = {}
    for row in run_log_rows:
        d = duration_ms(row)
        if d is not None:
            by_step.setdefault(row["step"], []).append(d)
    return [{"step": step, "n": len(ds), "mean_ms": round(statistics.fmean(ds), 1),
             "median_ms": round(statistics.median(ds), 1), "max_ms": round(max(ds), 1)}
            for step, ds in sorted(by_step.items())]


def rows_per_run(run_log_rows: list[dict]) -> list[dict]:
    """One row per run (file), from its Land step: how many records came in and landed.
    (Other steps count files or redacted fields, not records, so summing across steps
    would mix units.)"""
    land_rows = [r for r in run_log_rows if r["step"] == "land"]
    return sorted(
        [{"run_id": r["run_id"], "file_name": r["file_name"], "rows_in": r["rows_in"],
          "rows_out": r["rows_out"], "rows_rejected": r["rows_rejected"], "started_at": r["started_at"]}
         for r in land_rows],
        key=lambda r: r["started_at"] or "", reverse=True)
