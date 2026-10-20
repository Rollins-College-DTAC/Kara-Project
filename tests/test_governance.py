"""Tests for the Governance page's pure helpers (dashboard/governance.py)."""

from dashboard.governance import (incident_summary, latest_gold_scores, review_queue_summary,
                                  tokens_and_cost_on)


def eval_row(expert="haiku", metric="category_accuracy", value=0.85, evaluated_at="2026-01-01"):
    return {"expert": expert, "metric": metric, "value": value, "evaluated_at": evaluated_at}


def test_latest_gold_scores_keeps_only_the_most_recent_per_expert_and_metric():
    rows = [eval_row(evaluated_at="2026-01-01", value=0.80), eval_row(evaluated_at="2026-01-05", value=0.90),
           eval_row(expert="rules", evaluated_at="2026-01-01", value=0.70)]
    out = {(r["expert"], r["metric"]): r["value"] for r in latest_gold_scores(rows)}
    assert out[("haiku", "category_accuracy")] == 0.90
    assert out[("rules", "category_accuracy")] == 0.70


def usage_row(called_at, cached=0, input_tokens=100, output_tokens=50, cost=0.001):
    return {"called_at": called_at, "cached": cached, "input_tokens": input_tokens,
           "output_tokens": output_tokens, "estimated_cost_usd": cost}


def test_tokens_and_cost_on_only_counts_the_given_day():
    rows = [usage_row("2026-01-01T10:00:00"), usage_row("2026-01-02T10:00:00")]
    today = tokens_and_cost_on(rows, "2026-01-01")
    assert today["calls"] == 1 and today["tokens"] == 150 and today["cost_usd"] == 0.001


def test_tokens_and_cost_on_excludes_cache_hits_from_the_call_count():
    rows = [usage_row("2026-01-01T10:00:00", cached=0), usage_row("2026-01-01T11:00:00", cached=1,
                                                                   input_tokens=0, output_tokens=0, cost=0.0)]
    today = tokens_and_cost_on(rows, "2026-01-01")
    assert today["calls"] == 1  # the cache hit isn't a real call
    assert today["tokens"] == 150  # but both rows' tokens still sum correctly (cache hit is 0 anyway)


def test_incident_summary_groups_by_kind_and_status():
    rows = [{"kind": "trigger", "status": "open"}, {"kind": "trigger", "status": "open"},
           {"kind": "injection", "status": "open"}]
    counts = {(r["kind"], r["status"]): r["n"] for r in incident_summary(rows)}
    assert counts == {("trigger", "open"): 2, ("injection", "open"): 1}


def test_review_queue_summary_counts_by_status():
    rows = [{"status": "open"}, {"status": "open"}, {"status": "approved"}]
    assert review_queue_summary(rows) == {"open": 2, "approved": 1}
