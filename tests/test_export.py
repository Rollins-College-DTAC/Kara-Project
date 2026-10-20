"""Tests for agent/export.py: the daily summary a Claude Routine reads."""

from agent.db import connect
from agent.export import daily_summary, write_daily_summary
from agent.sql import now_iso


def test_daily_summary_is_empty_but_well_formed_with_no_data(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    summary = daily_summary(conn)
    assert summary["imports_processed_today"] == 0
    assert summary["held_imports"] == [] and summary["incidents_open"] == []
    assert summary["model_usage_by_expert_today"] == [] and summary["latest_published_batch"] is None


def test_daily_summary_counts_todays_landed_imports(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    conn.execute("INSERT INTO run_log (run_id, step, file_name, started_at) VALUES "
                "('r1', 'land', 'a.csv', ?), ('r2', 'land', 'b.csv', ?)", (now_iso(), now_iso()))
    conn.commit()
    assert daily_summary(conn)["imports_processed_today"] == 2


def test_daily_summary_lists_held_imports_grouped_by_file(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    conn.execute("INSERT INTO silver_records (file_name, row_index, run_id, status, consistency_ok, "
                "consistency_flags, landed_at) VALUES "
                "('a.csv', 0, 'r1', 'held', 1, '[]', ?), ('a.csv', 1, 'r1', 'held', 1, '[]', ?), "
                "('b.csv', 0, 'r1', 'published', 1, '[]', ?)", (now_iso(), now_iso(), now_iso()))
    conn.commit()
    held = daily_summary(conn)["held_imports"]
    assert held == [{"file_name": "a.csv", "n_held": 2}]


def test_daily_summary_flags_open_injection_and_failure_incidents_only(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    conn.execute("INSERT INTO incident_log (incident_id, run_id, kind, detail, status, opened_at) VALUES "
                "('i1', 'r1', 'injection', 'x', 'open', ?), "
                "('i2', 'r1', 'trigger', 'y', 'open', ?), "
                "('i3', 'r1', 'failure', 'z', 'released', ?)", (now_iso(), now_iso(), now_iso()))
    conn.commit()
    flags = daily_summary(conn)["ai_use_policy_flags"]
    assert [f["incident_id"] for f in flags] == ["i1"]  # trigger isn't a policy flag, failure isn't open


def test_write_daily_summary_writes_valid_json_to_the_given_path(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    out = tmp_path / "exports" / "daily_summary.json"
    summary = write_daily_summary(conn, out)
    import json
    assert json.loads(out.read_text(encoding="utf-8")) == json.loads(json.dumps(summary, default=str))
