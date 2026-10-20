"""Tests for scripts/injection_test.py: the prompt-injection test harness.

Runs with the kill switch off, so this exercises the rules expert's own injection regex --
free, deterministic, no key needed. This also double-checks a known, already-documented
result from milestone 3's evaluation: the rules expert catches the obvious injection styles
but misses the two subtle ones.
"""

import importlib.util

import pytest

from agent.config import ROOT, load_agent_config
from agent.db import connect
from generator.generate import INJECTION_NOTES


@pytest.fixture
def it():
    spec = importlib.util.spec_from_file_location("injection_test", ROOT / "scripts" / "injection_test.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_planted_file_writes_one_record_per_note(tmp_path, it):
    notes = INJECTION_NOTES[:3]
    path = it.build_planted_file(tmp_path / "inbox", notes)
    assert path.exists()
    import csv
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert [r["notes"] for r in rows] == notes


def test_run_quarantines_the_obvious_styles_and_misses_the_subtle_ones(tmp_path, it):
    cfg = load_agent_config()
    cfg["inbox"], cfg["processed"], cfg["quarantine"] = (tmp_path / "inbox", tmp_path / "processed",
                                                         tmp_path / "quarantine")
    cfg["data_dir"] = tmp_path / "data"
    cfg["sqlite_path"], cfg["raw_path"] = cfg["data_dir"] / "analytics.sqlite", cfg["data_dir"] / "raw.json"
    cfg["models"]["enabled"] = False  # the rules expert's own regex is what's under test

    report = it.run(cfg, INJECTION_NOTES)
    caught = [r["caught"] for r in report["results"]]
    assert caught == [True, True, True, False, False]  # matches milestone 3's documented 60% recall

    for r in report["results"]:
        if r["caught"]:
            assert r["status"] == "quarantined" and r["incident_logged"]


def test_summarize_reports_each_notes_own_row_even_when_most_are_missed(tmp_path, it):
    cfg = load_agent_config()
    cfg["inbox"], cfg["processed"], cfg["quarantine"] = (tmp_path / "inbox", tmp_path / "processed",
                                                         tmp_path / "quarantine")
    cfg["data_dir"] = tmp_path / "data"
    cfg["sqlite_path"], cfg["raw_path"] = cfg["data_dir"] / "analytics.sqlite", cfg["data_dir"] / "raw.json"
    cfg["models"]["enabled"] = False

    notes = [INJECTION_NOTES[0], "A perfectly ordinary note about scholarships and GPA."]
    report = it.run(cfg, notes)
    assert len(report["results"]) == 2
    assert report["results"][0]["caught"] is True
    assert report["results"][1]["caught"] is False  # not an injection at all; correctly not flagged
