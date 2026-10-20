"""Pure helpers for the Governance page (references/dashboard.md, references/governance.md):
gold-set scores per expert, cost against budget, review queue and incident summaries.
No Streamlit import, so these are testable without running the app.
"""

from __future__ import annotations


def latest_gold_scores(eval_log_rows: list[dict]) -> list[dict]:
    """The most recent score for each (expert, metric) pair, from eval_log -- a student
    re-runs scripts/evaluate.py as prompts change, so only the latest run per expert/metric
    reflects the current prompt version."""
    latest: dict[tuple[str, str], dict] = {}
    for row in eval_log_rows:
        key = (row["expert"], row["metric"])
        if key not in latest or row["evaluated_at"] > latest[key]["evaluated_at"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda r: (r["expert"], r["metric"]))


def tokens_and_cost_on(usage_rows: list[dict], day: str) -> dict:
    """day: 'YYYY-MM-DD'. Sums only real calls (a cache hit logs 0 tokens and 0 cost already,
    so including it is harmless, but cached=1 rows are kept out of the call count)."""
    todays = [r for r in usage_rows if (r["called_at"] or "").startswith(day)]
    return {
        "calls": sum(1 for r in todays if not r["cached"]),
        "tokens": sum((r["input_tokens"] or 0) + (r["output_tokens"] or 0) for r in todays),
        "cost_usd": round(sum(r["estimated_cost_usd"] or 0.0 for r in todays), 4),
    }


def incident_summary(incident_rows: list[dict]) -> list[dict]:
    counts: dict[tuple[str, str], int] = {}
    for r in incident_rows:
        key = (r["kind"], r["status"])
        counts[key] = counts.get(key, 0) + 1
    return [{"kind": k, "status": s, "n": n} for (k, s), n in sorted(counts.items())]


def review_queue_summary(review_rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for r in review_rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts
