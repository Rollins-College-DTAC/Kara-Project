"""Tests for the Models (MoE) page's pure helpers (dashboard/models.py)."""

from dashboard.models import per_expert_summary, task_expert_counts


def call(expert="haiku", task="classify", latency_ms=100, confidence=0.9, cached=0,
        input_tokens=50, output_tokens=20, estimated_cost_usd=0.001):
    return {"expert": expert, "task": task, "latency_ms": latency_ms, "confidence": confidence,
           "cached": cached, "input_tokens": input_tokens, "output_tokens": output_tokens,
           "estimated_cost_usd": estimated_cost_usd}


def test_per_expert_summary_sums_tokens_and_cost():
    rows = [call(expert="haiku"), call(expert="haiku"), call(expert="rules", input_tokens=0,
                                                               output_tokens=0, estimated_cost_usd=0.0,
                                                               confidence=None)]
    summary = {s["expert"]: s for s in per_expert_summary(rows)}
    assert summary["haiku"]["calls"] == 2 and summary["haiku"]["tokens"] == 140
    assert summary["haiku"]["cost_usd"] == 0.002
    assert summary["rules"]["calls"] == 1 and summary["rules"]["avg_confidence"] is None


def test_per_expert_summary_excludes_cache_hits_from_average_latency():
    rows = [call(latency_ms=200, cached=0), call(latency_ms=0, cached=1)]
    summary = per_expert_summary(rows)[0]
    assert summary["calls"] == 2  # a cache hit still counts as a call
    assert summary["avg_latency_ms"] == 200.0  # but doesn't drag the latency average toward 0


def test_per_expert_summary_sorts_by_calls_descending():
    rows = [call(expert="rules"), call(expert="haiku"), call(expert="haiku")]
    assert [s["expert"] for s in per_expert_summary(rows)] == ["haiku", "rules"]


def test_task_expert_counts_groups_correctly():
    rows = [call(task="classify", expert="haiku"), call(task="classify", expert="haiku"),
           call(task="extract", expert="rules")]
    counts = {(r["task"], r["expert"]): r["count"] for r in task_expert_counts(rows)}
    assert counts == {("classify", "haiku"): 2, ("extract", "rules"): 1}
