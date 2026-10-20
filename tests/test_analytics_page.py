"""Tests for the Analytics page's pure helper (dashboard/analytics.py): trigger precision/recall."""

from dashboard.analytics import trigger_precision_recall


def gen(file_name, expected_detector=""):
    return {"file_name": file_name, "expected_detector": expected_detector}


def dec(file_name, fired):
    return {"file_name": file_name, "fired": fired}


def test_a_caught_real_anomaly_is_a_true_positive():
    pr = trigger_precision_recall([dec("a.csv", True)], [gen("a.csv", "zscore")])
    assert pr == {"tp": 1, "fp": 0, "fn": 0, "tn": 0, "precision": 1.0, "recall": 1.0}


def test_a_missed_real_anomaly_is_a_false_negative():
    pr = trigger_precision_recall([dec("a.csv", False)], [gen("a.csv", "zscore")])
    assert pr["fn"] == 1 and pr["recall"] == 0.0


def test_firing_on_a_clean_import_is_a_false_positive():
    pr = trigger_precision_recall([dec("a.csv", True)], [gen("a.csv", "")])
    assert pr["fp"] == 1 and pr["precision"] == 0.0


def test_consistency_check_anomalies_count_as_ground_truth_negative():
    """A counts_exceed_class anomaly is Load's job, not this trigger's -- not firing on it
    is correct behavior for the z-score detector, a true negative."""
    pr = trigger_precision_recall([dec("a.csv", False)], [gen("a.csv", "consistency_check")])
    assert pr["tn"] == 1 and pr["fp"] == 0 and pr["fn"] == 0


def test_a_decision_with_no_matching_generator_row_is_skipped():
    pr = trigger_precision_recall([dec("unknown.csv", True)], [gen("a.csv", "zscore")])
    assert pr == {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "precision": None, "recall": None}


def test_precision_and_recall_with_a_mixed_batch():
    decisions = [dec("spike.csv", True), dec("drop.csv", False), dec("clean.csv", True), dec("clean2.csv", False)]
    generator = [gen("spike.csv", "zscore"), gen("drop.csv", "zscore"), gen("clean.csv", ""), gen("clean2.csv", "")]
    pr = trigger_precision_recall(decisions, generator)
    assert pr["tp"] == 1 and pr["fn"] == 1 and pr["fp"] == 1 and pr["tn"] == 1
    assert pr["precision"] == 0.5 and pr["recall"] == 0.5
