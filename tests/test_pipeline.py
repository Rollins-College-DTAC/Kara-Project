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
