"""Tests for dashboard/ui.py: the HTML builders. Pure strings, so these check structure,
escaping, and the markdown-safety rule (no newlines or blank lines that Streamlit would turn
into code blocks)."""

from datetime import date

from dashboard.ui import (cost_tone, employment_bar, employment_tone, money, odds_tone, pct, pill,
                          school_card, stat_card, status_tone, timeline)


def test_school_names_are_html_escaped():
    card = school_card(name='<script>alert("x")</script>', code="LS-01", rank=1, status="Draft", odds="Reach",
                       lsat=160, gpa=3.5, cost=50000, offer=None, net=50000, emp_rate=0.6, breakdown=None)
    assert "<script>" not in card and "&lt;script&gt;" in card


def test_builders_emit_no_newlines_so_markdown_cannot_make_code_blocks():
    card = school_card(name="X", code="LS-01", rank=2, status="Accepted", odds="Safe", lsat=160, gpa=3.5,
                       cost=50000, offer=10000, net=40000, emp_rate=0.7,
                       breakdown={"bar_required": .7, "jd_advantage": .15, "other": .1, "unemployed": .05})
    for html_text in (card, stat_card("a", "b", "c"), employment_bar({"bar_required": 1.0}),
                      timeline([(date(2026, 12, 1), "Application", "X")], date(2026, 11, 10))):
        assert "\n" not in html_text


def test_pill_uses_the_tone_colors():
    assert "#2F7A5A" in pill("Accepted", "good")
    assert "#A83A48" in pill("Late", "bad")


def test_status_and_odds_tones():
    assert status_tone("Accepted") == "good" and status_tone("Waitlisted") == "warn"
    assert odds_tone("Safe") == "good" and odds_tone("Reach") == "warn" and odds_tone(None) == "neutral"


def test_employment_and_cost_tone_thresholds():
    assert employment_tone(0.7) == "good" and employment_tone(0.55) == "warn" and employment_tone(0.4) == "bad"
    assert employment_tone(None) == "neutral"
    assert cost_tone(20000) == "good" and cost_tone(35000) == "warn" and cost_tone(60000) == "bad"


def test_money_and_pct_format_and_handle_missing():
    assert money(31200) == "$31,200" and money(None) == "—"
    assert pct(0.638) == "63.8%" and pct(None) == "—"


def test_employment_bar_segments_sum_to_full_width():
    out = employment_bar({"bar_required": .5, "jd_advantage": .3, "other": .1, "unemployed": .1})
    widths = [float(w) for w in __import__("re").findall(r"width:([\d.]+)%", out)]
    assert round(sum(widths)) == 100


def test_employment_bar_handles_no_data():
    assert "No employment breakdown" in employment_bar(None)


def test_timeline_colors_by_urgency_and_labels_days():
    today = date(2026, 11, 10)
    out = timeline([(date(2026, 11, 15), "Application", "A"), (date(2026, 12, 5), "FAFSA", "B"),
                    (date(2027, 2, 1), "Seat deposit", "C")], today)
    assert "in 5 days" in out and "#A83A48" in out and "#9A6410" in out and "#2F7A5A" in out


def test_timeline_empty_state():
    assert "No upcoming deadlines" in timeline([], date(2026, 11, 10))


# ---------------------------------------------------------------- animated pieces

from dashboard.ui import counter, hero, ring  # noqa: E402


def test_ring_encodes_the_value_as_a_dash_offset_and_stays_one_line():
    out = ring(0.75, "good", "employed")
    assert "\n" not in out and "75.0%" in out
    c = float(out.split("--c:")[1].split(";")[0])
    off = float(out.split("--off:")[1].split('"')[0])
    assert abs(off - c * 0.25) < 0.05


def test_ring_clamps_out_of_range_and_handles_missing():
    assert "--off:0.00" in ring(1.7, "good", "x")
    assert "—" in ring(None, "neutral", "x")


def test_counter_carries_the_target_number_for_the_css_count_up():
    assert 'style="--to:164"' in counter(164) and 'aria-label="164"' in counter(164)


def test_hero_escapes_text_and_renders_kpis():
    out = hero("<b>Title</b>", "sub", [("Imports", "12", "files")])
    assert "&lt;b&gt;" in out and "<b>Title" not in out and "Imports" in out and "\n" not in out


def test_stat_card_can_count_up():
    from dashboard.ui import stat_card
    assert "cu" in stat_card("Schools", "6", count_to=6)
