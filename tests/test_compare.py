"""Tests for the Compare Schools page's pure helpers (dashboard/compare.py)."""

import pytest

from dashboard.compare import build_school_profiles


def rec(school_code="LS-01", school_name="Marrowbrook School of Law", grads=100, emp_bar_required=70,
       class_size=120, acceptance_rate=0.4, lsat_50=160, gpa_50=3.5, scholarship_share=0.3,
       cost_of_attendance=50000, bar_pass_rate=0.85):
    return {"school_code": school_code, "school_name": school_name, "grads": grads,
           "emp_bar_required": emp_bar_required, "class_size": class_size,
           "acceptance_rate": acceptance_rate, "lsat_50": lsat_50, "gpa_50": gpa_50,
           "scholarship_share": scholarship_share, "cost_of_attendance": cost_of_attendance,
           "bar_pass_rate": bar_pass_rate}


def test_build_school_profiles_averages_across_multiple_records():
    rows = [rec(cost_of_attendance=48000, lsat_50=158), rec(cost_of_attendance=52000, lsat_50=162)]
    profiles = build_school_profiles(rows)
    p = profiles["LS-01"]
    assert p.n == 2 and p.cost_of_attendance == 50000 and p.lsat_50 == 160


def test_build_school_profiles_sums_emp_rate_across_records_not_averaging_per_record_rates():
    """emp_rate must be computed from summed grads/bar_required, not averaged per-record
    rates, so a bigger import doesn't get diluted by a smaller one."""
    rows = [rec(grads=100, emp_bar_required=90), rec(grads=10, emp_bar_required=1)]
    p = build_school_profiles(rows)["LS-01"]
    assert p.emp_rate == pytest.approx(91 / 110, abs=1e-4)  # emp_rate is rounded to 4 places


def test_build_school_profiles_skips_rows_with_no_school_code():
    rows = [rec(school_code=None), rec()]
    assert len(build_school_profiles(rows)) == 1


def test_est_net_cost_is_cost_times_one_minus_scholarship_share():
    p = build_school_profiles([rec(cost_of_attendance=60000, scholarship_share=0.25)])["LS-01"]
    assert p.est_net_cost == 45000.0


def test_est_net_cost_is_none_without_both_inputs():
    rows = [{"school_code": "LS-01", "school_name": "X", "grads": 100, "emp_bar_required": 70,
            "cost_of_attendance": None, "scholarship_share": 0.3}]
    assert build_school_profiles(rows)["LS-01"].est_net_cost is None


def test_value_index_is_emp_rate_per_10k_of_net_cost():
    p = build_school_profiles([rec(grads=100, emp_bar_required=70, cost_of_attendance=70000,
                                   scholarship_share=0.0)])["LS-01"]
    assert p.est_net_cost == 70000.0
    assert p.value_index == pytest.approx(0.7 / 7)  # emp_rate 0.7 / (70000/10000)


def test_value_index_is_none_when_net_cost_is_zero_or_missing():
    p = build_school_profiles([rec(cost_of_attendance=0, scholarship_share=1.0)])["LS-01"]
    assert p.est_net_cost == 0.0 and p.value_index is None


def test_two_schools_compare_sensibly_cheaper_and_better_outcomes_scores_higher():
    cheap_better = rec(school_code="LS-01", grads=100, emp_bar_required=80, cost_of_attendance=30000,
                       scholarship_share=0.5)
    pricey_worse = rec(school_code="LS-02", grads=100, emp_bar_required=50, cost_of_attendance=70000,
                       scholarship_share=0.0)
    profiles = build_school_profiles([cheap_better, pricey_worse])
    assert profiles["LS-01"].value_index > profiles["LS-02"].value_index


# ---------------------------------------------------------------- rank, odds, employment breakdown

from dashboard.compare import admission_odds, rank_by_lsat  # noqa: E402


def test_emp_breakdown_shares_are_computed_from_summed_counts_and_sum_to_one():
    rows = [dict(rec(grads=100, emp_bar_required=60), emp_jd_advantage=20, emp_other=15, emp_unemployed=5),
            dict(rec(grads=100, emp_bar_required=80), emp_jd_advantage=10, emp_other=5, emp_unemployed=5)]
    b = build_school_profiles(rows)["LS-01"].emp_breakdown
    assert b == {"bar_required": 0.7, "jd_advantage": 0.15, "other": 0.1, "unemployed": 0.05}
    assert sum(b.values()) == pytest.approx(1.0)


def test_rank_by_lsat_orders_by_median_lsat_then_employment():
    rows = [rec("LS-01", lsat_50=165), rec("LS-02", lsat_50=170), rec("LS-03", lsat_50=165, emp_bar_required=90)]
    ranks = rank_by_lsat(build_school_profiles(rows))
    assert ranks == {"LS-02": 1, "LS-03": 2, "LS-01": 3}


def test_admission_odds_reach_target_safe():
    assert admission_odds(175, 3.95, 160, 3.5) == "Safe"
    assert admission_odds(160, 3.5, 160, 3.5) == "Target"
    assert admission_odds(150, 3.0, 165, 3.7) == "Reach"


def test_admission_odds_without_gpa_uses_lsat_alone_and_none_without_school_data():
    assert admission_odds(170, None, 160, None) == "Safe"
    assert admission_odds(170, 3.9, None, None) is None
