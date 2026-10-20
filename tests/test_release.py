"""Tests for agent/release.py: the dashboard's Release/Reject action on a trigger-held import."""

import pytest

from agent.db import connect
from agent.release import reject_import, release_import
from agent.sql import now_iso


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def seed_held_import(conn, file_name, run_id="run-x", n_trigger=3, n_consistency=1):
    """A trigger-held import (plus one unrelated, still-broken consistency row that must
    never be released alongside it)."""
    for i in range(n_trigger):
        conn.execute(
            "INSERT INTO silver_records (file_name, row_index, run_id, school_code, grads, "
            "emp_bar_required, emp_rate, consistency_ok, consistency_flags, status, landed_at) "
            "VALUES (?, ?, ?, 'LS-01', 100, 90, 0.9, 1, '[]', 'held', ?)",
            (file_name, i, run_id, now_iso()))
    for i in range(n_consistency):
        conn.execute(
            "INSERT INTO silver_records (file_name, row_index, run_id, school_code, grads, "
            "emp_bar_required, emp_rate, consistency_ok, consistency_flags, status, landed_at) "
            "VALUES (?, ?, ?, 'LS-02', 100, 900, NULL, 0, '[\"counts_exceed_class\"]', 'held', ?)",
            (file_name, 100 + i, run_id, now_iso()))
    conn.execute("INSERT INTO run_log (run_id, step, file_name, started_at) VALUES (?, 'decide', ?, ?)",
                 (run_id, file_name, now_iso()))
    conn.execute("INSERT INTO incident_log (incident_id, run_id, kind, detail, status, opened_at) "
                "VALUES (?, ?, 'trigger', ?, 'open', ?)",
                (f"inc-{file_name}", run_id, f"{file_name}: anomaly trigger fired", now_iso()))
    conn.commit()


def test_release_requires_a_name(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    seed_held_import(conn, "f.csv")
    with pytest.raises(ValueError, match="decided_by"):
        release_import(conn, "f.csv", "  ")


def test_release_publishes_only_the_trigger_held_rows(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    seed_held_import(conn, "f.csv")
    n = release_import(conn, "f.csv", "KB")
    assert n == 3
    statuses = rows(conn, "SELECT consistency_ok, status FROM silver_records WHERE file_name = 'f.csv'")
    published = [r for r in statuses if r["consistency_ok"] == 1]
    broken = [r for r in statuses if r["consistency_ok"] == 0]
    assert all(r["status"] == "published" for r in published)
    assert all(r["status"] == "held" for r in broken)  # untouched: a separate problem

    incident = rows(conn, "SELECT * FROM incident_log WHERE kind = 'trigger'")[0]
    assert incident["status"] == "released" and incident["decided_by"] == "KB" and incident["closed_at"]


def test_reject_excludes_rows_instead_of_publishing(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    seed_held_import(conn, "g.csv", run_id="run-y")
    n = reject_import(conn, "g.csv", "KB")
    assert n == 3
    statuses = {r["status"] for r in rows(conn, "SELECT status FROM silver_records "
                                                "WHERE file_name = 'g.csv' AND consistency_ok = 1")}
    assert statuses == {"rejected"}
    incident = rows(conn, "SELECT * FROM incident_log WHERE kind = 'trigger'")[0]
    assert incident["status"] == "rejected"


def test_releasing_an_already_resolved_import_is_a_no_op(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    seed_held_import(conn, "h.csv", run_id="run-z")
    release_import(conn, "h.csv", "KB")
    n = release_import(conn, "h.csv", "KB")  # clicked twice, or a stale page
    assert n == 0
