"""Real-data Compare page pieces: profile pooling, national trend, sparkline, chips, trend chart."""

from dashboard.charts import employment_trend_chart
from dashboard.compare import build_real_profiles, national_trend
from dashboard.ui import chips, school_card, sparkline


def emp(code, year, grads, bar, **kw):
    row = {"school_code": code, "grad_year": year, "grads": grads, "emp_bar_required": bar,
           "emp_jd_advantage": 0, "emp_other": 0, "emp_unemployed": 0, "emp_biglaw": 0,
           "emp_fed_clerkship": 0, "emp_public_interest": 0, "emp_government": 0, "emp_business": 0}
    row.update(kw)
    return row


PROFILE = {"school_key": "a", "school_name": "A Law", "school_type": "Public", "enrollees": 100,
           "acceptance_rate": 0.4, "lsat_50": 165, "gpa_50": 3.7, "grants_share": 0.5, "tuition_resident": 30000,
           "fees": 1000, "bar_first_time_pass": 0.9, "bar_state_avg": 0.8, "est_net_tuition": 25000}
ROWS = [emp("a", 2022, 100, 50), emp("a", 2023, 100, 60), emp("a", 2024, 300, 240, emp_biglaw=30),
        emp("a", 2025, 100, 80, emp_biglaw=10), emp("b", 2025, 100, 10)]


def test_pools_latest_three_classes_by_counts():
    p = build_real_profiles([PROFILE], ROWS, window=3)["a"]
    assert p.years == (2023, 2025)
    assert p.emp_rate == round((60 + 240 + 80) / 500, 4)  # pooled counts, not a mean of rates
    assert [y for y, _ in p.trend] == [2022, 2023, 2024, 2025]
    assert p.employer_shares["biglaw"] == round(40 / 500, 4)
    assert p.cost_of_attendance == 31000 and p.est_net_cost == 25000
    assert p.bar_state_avg == 0.8 and p.school_type == "Public"


def test_school_without_employment_rows_is_still_listed():
    p = build_real_profiles([PROFILE], [], window=3)["a"]
    assert p.emp_rate is None and p.trend == [] and p.years is None


def test_national_trend_pools_all_schools():
    t = dict(national_trend(ROWS))
    assert t[2025] == round(90 / 200, 4) and t[2022] == 0.5


def test_sparkline_needs_two_points_and_escapes_nothing_unsafe():
    assert sparkline([(2024, 0.5)]) == "" and sparkline(None) == ""
    html = sparkline([(2022, 0.5), (2023, 0.6), (2024, None), (2025, 0.8)])
    assert "<path" in html and "2022" in html and "\n" not in html


def test_chips_skip_zero_shares():
    html = chips({"biglaw": 0.08, "fed_clerkship": 0, "government": None})
    assert "501+ firms" in html and "Federal" not in html and chips({}) == ""


def test_real_card_has_no_sample_labels():
    html = school_card(name="A", code="", rank=3, rank_label="by median LSAT", status=None, odds="Target",
                       lsat=165, gpa=3.7, cost=None, offer=None, net=25000, emp_rate=0.76, breakdown=None,
                       school_type="Public", trend=[(2024, 0.7), (2025, 0.76)], bar_pass=0.9, bar_state_avg=0.8)
    assert "by median LSAT" in html and "(sample)" not in html and "Public" in html
    assert "Bar passage" in html and "no offer yet" not in html


def test_trend_chart_builds_and_handles_empty():
    assert employment_trend_chart({"All schools": []}) is None
    chart = employment_trend_chart({"All schools": [(2024, 0.7), (2025, 0.72)], "A": [(2024, 0.8), (2025, 0.9)]})
    assert chart.to_dict()["layer"]
