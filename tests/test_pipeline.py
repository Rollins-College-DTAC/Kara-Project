"""Tests for the Pipeline History page's pure helpers (dashboard/pipeline.py)."""

from dashboard.pipeline import duration_ms, rows_per_run, step_duration_summary


def test_duration_ms_computes_the_elapsed_time():
    row = {"started_at": "2026-01-01T00:00:00.000+00:00", "finished_at": "2026-01-01T00:00:01.500+00:00"}
    assert duration_ms(row) == 1500.0


def test_duration_ms_is_none_for_a_still_running_step():
    assert duration_ms({"started_at": "2026-01-01T00:00:00.000+00:00", "finished_at": None}) is None


def test_step_duration_summary_aggregates_per_step_not_per_run():
    rows = [
        {"step": "detect", "started_at": "2026-01-01T00:00:00.000+00:00", "finished_at": "2026-01-01T00:00:00.100+00:00"},
        {"step": "detect", "started_at": "2026-01-01T00:01:00.000+00:00", "finished_at": "2026-01-01T00:01:00.300+00:00"},
        {"step": "land", "started_at": "2026-01-01T00:00:00.000+00:00", "finished_at": "2026-01-01T00:00:00.500+00:00"},
    ]
    summary = {s["step"]: s for s in step_duration_summary(rows)}
    assert summary["detect"]["n"] == 2 and summary["detect"]["mean_ms"] == 200.0
    assert summary["land"]["n"] == 1 and summary["land"]["max_ms"] == 500.0


def test_step_duration_summary_skips_rows_with_no_finish_time():
    rows = [{"step": "detect", "started_at": "2026-01-01T00:00:00.000+00:00", "finished_at": None}]
    assert step_duration_summary(rows) == []


def test_rows_per_run_only_reads_the_land_step_and_sorts_newest_first():
    rows = [
        {"step": "detect", "run_id": "r1", "file_name": "a.csv", "rows_in": 1, "rows_out": 1,
         "rows_rejected": 0, "started_at": "2026-01-01T00:00:00"},
        {"step": "land", "run_id": "r1", "file_name": "a.csv", "rows_in": 10, "rows_out": 10,
         "rows_rejected": 0, "started_at": "2026-01-01T00:00:00"},
        {"step": "land", "run_id": "r2", "file_name": "b.csv", "rows_in": 8, "rows_out": 7,
         "rows_rejected": 1, "started_at": "2026-01-01T00:01:00"},
    ]
    result = rows_per_run(rows)
    assert [r["run_id"] for r in result] == ["r2", "r1"]
    assert result[1] == {"run_id": "r1", "file_name": "a.csv", "rows_in": 10, "rows_out": 10,
                         "rows_rejected": 0, "started_at": "2026-01-01T00:00:00"}


def test_overview_counts_summarises_the_database(tmp_path):
    from agent.db import connect
    from agent.sql import now_iso
    from dashboard.db import overview_counts
    conn = connect(tmp_path / "d.sqlite")
    conn.execute("INSERT INTO run_log (run_id, step, file_name, started_at) VALUES ('r', 'land', 'a.csv', ?)", (now_iso(),))
    conn.execute("INSERT INTO silver_records (file_name, row_index, run_id, status, consistency_ok, consistency_flags, landed_at) "
                 "VALUES ('a.csv', 0, 'r', 'published', 1, '[]', ?), ('a.csv', 1, 'r', 'held', 1, '[]', ?)", (now_iso(), now_iso()))
    conn.execute("INSERT INTO decision_log (run_id, file_name, rule, statistic, fired, action, decided_at) "
                 "VALUES ('r', 'a.csv', 'anomaly', 2.5, 0, 'publish', ?)", (now_iso(),))
    conn.commit()
    c = overview_counts(conn)
    assert c == {"files": 1, "published": 1, "held": 1, "open_incidents": 0, "last_z": 2.5}
