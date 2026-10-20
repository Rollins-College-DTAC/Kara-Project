"""Pure helpers for the Models (MoE) page (references/dashboard.md, references/models-moe.md):
per-expert summary and the task-to-expert flow. No Streamlit import, so these are testable
without running the app.
"""

from __future__ import annotations

import statistics


def per_expert_summary(usage_rows: list[dict]) -> list[dict]:
    """calls, average latency (over real calls only -- a cache hit logs 0ms, which would
    misleadingly pull the average toward zero), average confidence, tokens, estimated cost."""
    by_expert: dict[str, dict] = {}
    for r in usage_rows:
        d = by_expert.setdefault(r["expert"], {"calls": 0, "tokens": 0, "cost_usd": 0.0, "lat": [], "conf": []})
        d["calls"] += 1
        d["tokens"] += (r["input_tokens"] or 0) + (r["output_tokens"] or 0)
        d["cost_usd"] += r["estimated_cost_usd"] or 0.0
        if not r["cached"]:
            d["lat"].append(r["latency_ms"] or 0)
        if r["confidence"] is not None:
            d["conf"].append(r["confidence"])
    out = [{"expert": expert, "calls": d["calls"],
           "avg_latency_ms": round(statistics.fmean(d["lat"]), 1) if d["lat"] else None,
           "avg_confidence": round(statistics.fmean(d["conf"]), 3) if d["conf"] else None,
           "tokens": d["tokens"], "cost_usd": round(d["cost_usd"], 4)}
          for expert, d in by_expert.items()]
    return sorted(out, key=lambda r: -r["calls"])


def task_expert_counts(usage_rows: list[dict]) -> list[dict]:
    """How many calls of each task went to each expert, for a grouped bar chart."""
    counts: dict[tuple[str, str], int] = {}
    for r in usage_rows:
        key = (r["task"], r["expert"])
        counts[key] = counts.get(key, 0) + 1
    return [{"task": t, "expert": e, "count": c} for (t, e), c in sorted(counts.items())]
