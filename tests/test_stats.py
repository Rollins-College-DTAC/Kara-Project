"""Tests for milestone 4 stage 2: Wilson CI, two-proportion test, correlation/regression.

Pure math, no network, no model calls. Known-value checks against hand-computed references
plus sanity checks (perfect correlation, no-difference proportions) a formula bug would break.
"""

import math

import pytest

from agent.stats import (aggregate_by_school, compute_all, correlation_and_regression,
                          employment_rate_ci, two_proportion_test, wilson_interval)


def test_wilson_interval_matches_a_known_reference():
    # p=0.5, n=100, z=1.96: textbook Wilson interval is approximately (0.404, 0.596).
    lo, hi = wilson_interval(50, 100)
    assert lo == pytest.approx(0.404, abs=0.001) and hi == pytest.approx(0.596, abs=0.001)


def test_wilson_interval_stays_inside_0_1_even_at_the_extremes():
    lo, hi = wilson_interval(0, 5)
    assert 0.0 <= lo <= hi <= 1.0
    lo, hi = wilson_interval(5, 5)
    assert 0.0 <= lo <= hi <= 1.0


def test_wilson_interval_is_undefined_for_zero_n():
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_employment_rate_ci_shape_and_interpretation():
    stat = employment_rate_ci("LS-01", 70, 100)
    assert stat["method"] == "wilson_ci" and stat["result"] == 0.7
    assert stat["inputs"]["ci_low"] < 0.7 < stat["inputs"]["ci_high"]
    assert "LS-01" in stat["interpretation"] and "70.0%" in stat["interpretation"]


def test_two_proportion_test_detects_a_large_difference():
    stat = two_proportion_test("public", 90, 100, "private", 50, 100)
    assert stat["result"] > 3  # a 40-point gap at n=100 each is many standard errors
    assert stat["p_value"] < 0.001
    assert "significant difference" in stat["interpretation"] and "no statistically" not in stat["interpretation"]


def test_two_proportion_test_finds_no_difference_for_identical_rates():
    stat = two_proportion_test("public", 50, 100, "private", 50, 100)
    assert stat["result"] == 0.0 and stat["p_value"] == pytest.approx(1.0, abs=1e-9)
    assert "no statistically significant difference" in stat["interpretation"]


def test_correlation_and_regression_perfect_positive_line():
    xs = [150, 155, 160, 165, 170]
    ys = [0.5, 0.6, 0.7, 0.8, 0.9]  # exactly +0.02 per LSAT point
    stat = correlation_and_regression("median LSAT", "employment rate", xs, ys)
    assert stat["result"] == pytest.approx(1.0, abs=1e-9)
    assert stat["inputs"]["slope"] == pytest.approx(0.02, abs=1e-6)


def test_correlation_and_regression_perfect_negative_line():
    xs = [150, 155, 160, 165, 170]
    ys = [0.9, 0.8, 0.7, 0.6, 0.5]
    stat = correlation_and_regression("median LSAT", "employment rate", xs, ys)
    assert stat["result"] == pytest.approx(-1.0, abs=1e-9)


def test_correlation_and_regression_zero_variance_x_does_not_crash():
    stat = correlation_and_regression("x", "y", [160, 160, 160], [0.5, 0.6, 0.7])
    assert stat["result"] == 0.0  # no correlation is computable when x never varies


# ---------------------------------------------------------------- aggregate_by_school / compute_all

def _row(school_code="LS-01", grads=100, bar_required=70, lsat_50=160):
    return {"school_code": school_code, "grads": grads, "emp_bar_required": bar_required, "lsat_50": lsat_50}


def test_aggregate_by_school_sums_across_multiple_imports():
    rows = [_row(grads=100, bar_required=60, lsat_50=158), _row(grads=50, bar_required=40, lsat_50=162)]
    agg = aggregate_by_school(rows)
    assert agg["LS-01"].grads == 150 and agg["LS-01"].bar_required == 100
    assert agg["LS-01"].median_lsat_50 == 160  # median of 158, 162
    assert agg["LS-01"].emp_rate == pytest.approx(100 / 150)


def test_aggregate_by_school_skips_rows_missing_identity_or_counts():
    rows = [_row(school_code=None), _row(grads=0), {"school_code": "LS-02", "grads": 10,
                                                      "emp_bar_required": None, "lsat_50": 160}]
    assert aggregate_by_school(rows) == {}


def test_compute_all_returns_ci_per_school_plus_group_test_plus_correlation():
    # 5 public, 5 private schools (by generator/schools.json's own type labels) with different rates,
    # so every branch of compute_all (per-school CI, two-proportion, correlation) has enough data.
    import random

    from generator.generate import load_schools
    schools = load_schools()
    public = [s for s in schools if s["type"] == "public"][:5]
    private = [s for s in schools if s["type"] == "private"][:5]
    r = random.Random(1)
    rows = []
    for s in public:
        rows.append(_row(s["code"], grads=100, bar_required=80, lsat_50=r.randint(150, 160)))
    for s in private:
        rows.append(_row(s["code"], grads=100, bar_required=50, lsat_50=r.randint(160, 170)))

    results = compute_all(rows)
    methods = [r["method"] for r in results]
    assert methods.count("wilson_ci") == 10
    assert "two_proportion_z_test" in methods
    assert "pearson_correlation_and_regression" in methods
    two_prop = next(r for r in results if r["method"] == "two_proportion_z_test")
    assert two_prop["p_value"] < 0.05  # 80% vs 50% across n=500 each is a real difference


def test_compute_all_skips_group_test_and_correlation_with_too_little_data():
    results = compute_all([_row("LS-01", grads=10, bar_required=7, lsat_50=160)])
    methods = [r["method"] for r in results]
    assert methods == ["wilson_ci"]  # only one school, one type: nothing to compare or correlate
