"""Tests for dashboard/charts.py: the interactive Altair spec."""

from dashboard.charts import short_name, value_bubble_chart

PTS = [
    {"school": "Ardenbrook College of Law", "code": "LS-15", "net_cost": 30000, "emp_rate": 0.64,
     "class_size": 200, "value_index": 0.21, "rank": 3},
    {"school": "Marrowbrook School of Law", "code": "LS-01", "net_cost": 50000, "emp_rate": 0.55,
     "class_size": 300, "value_index": 0.11, "rank": 9},
]


def test_short_name_drops_generic_suffixes():
    assert short_name("Ardenbrook College of Law") == "Ardenbrook"
    assert short_name("Calder State University College of Law") == "Calder"


def test_chart_is_none_without_plottable_points():
    assert value_bubble_chart([]) is None
    assert value_bubble_chart([{"school": "X", "code": "LS-01", "net_cost": None, "emp_rate": 0.5}]) is None


def test_chart_spec_has_tooltips_hover_selection_and_mean_guides():
    spec = value_bubble_chart(PTS).to_dict()
    text = str(spec)
    assert "mouseover" in text and "Employment rate" in text and "Value index" in text
    assert len(spec["layer"]) == 5  # two guides, bubbles, labels, corner note


def test_missing_class_size_and_value_index_do_not_break_the_spec():
    pts = [{**PTS[0], "class_size": None, "value_index": None}]
    assert value_bubble_chart(pts).to_dict()["layer"]
