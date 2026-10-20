"""Tests for the Data page's pure data-quality helpers (dashboard/quality.py)."""

from dashboard.quality import flag_counts, status_breakdown


def rec(status="published", consistency_ok=1, flags=None):
    return {"status": status, "consistency_ok": consistency_ok, "consistency_flags": flags or "[]"}


def test_flag_counts_ignores_consistent_records():
    rows = [rec(), rec(consistency_ok=0, flags='["counts_exceed_class"]')]
    assert flag_counts(rows) == {"counts_exceed_class": 1}


def test_flag_counts_counts_a_record_with_two_broken_rules_under_both():
    rows = [rec(consistency_ok=0, flags='["categories_dont_sum", "percentiles_out_of_order"]')]
    assert flag_counts(rows) == {"categories_dont_sum": 1, "percentiles_out_of_order": 1}


def test_flag_counts_empty_for_no_broken_records():
    assert flag_counts([rec(), rec()]) == {}


def test_status_breakdown_counts_each_status():
    rows = [rec(status="published"), rec(status="published"), rec(status="held")]
    assert status_breakdown(rows) == {"published": 2, "held": 1}
