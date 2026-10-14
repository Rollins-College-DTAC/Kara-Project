"""Tests for milestone 4 stage 3: the anomaly trigger, Decide and Act.

No model calls, no network: the trigger only reads silver_records, which stage 1's Load
step already populates independent of any Claude call.
"""

from agent.db import connect
from agent.decide import Z_THRESHOLD, decide_and_act
from agent.sql import RunContext, new_run_id, now_iso


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def seed_published(conn, file_name, emp_rate, index):
    """A row as if an earlier import had already been decided and published."""
    conn.execute(
        "INSERT INTO silver_records (file_name, row_index, run_id, school_code, grads, emp_bar_required, "
        "emp_rate, consistency_ok, consistency_flags, status, landed_at) "
        "VALUES (?, 0, 'seed', 'LS-01', 100, ?, ?, 1, '[]', 'published', ?)",
        (file_name, round(emp_rate * 100), emp_rate, f"2026-01-01T00:00:00.{index:06d}"))
    conn.commit()


def seed_pending(conn, file_name, emp_rate, n=1):
    for i in range(n):
        conn.execute(
            "INSERT INTO silver_records (file_name, row_index, run_id, school_code, grads, emp_bar_required, "
            "emp_rate, consistency_ok, consistency_flags, status, landed_at) "
            "VALUES (?, ?, 'seed', 'LS-01', 100, ?, ?, 1, '[]', 'pending', ?)",
            (file_name, i, round(emp_rate * 100), emp_rate, now_iso()))
    conn.commit()


def ctx_for(conn, file_name):
    return RunContext(conn=conn, run_id=new_run_id(), file_name=file_name)


def test_too_little_history_auto_publishes(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    for i in range(3):
        seed_published(conn, f"hist-{i}.csv", 0.5, i)
    seed_pending(conn, "today.csv", 0.9)  # would look extreme, but there isn't enough history yet
    result = decide_and_act(ctx_for(conn, "today.csv"))
    assert result["fired"] is False and result["action"] == "publish"
    assert rows(conn, "SELECT status FROM silver_records WHERE file_name='today.csv'")[0]["status"] == "published"
    dec = rows(conn, "SELECT * FROM decision_log WHERE file_name='today.csv'")[0]
    assert dec["fired"] == 0 and "need 5" in dec["detail"]


def test_normal_batch_does_not_fire(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    for i in range(10):
        seed_published(conn, f"hist-{i}.csv", 0.50 + (0.01 if i % 2 else -0.01), i)
    seed_pending(conn, "today.csv", 0.51)
    result = decide_and_act(ctx_for(conn, "today.csv"))
    assert result["fired"] is False
    assert rows(conn, "SELECT status FROM silver_records WHERE file_name='today.csv'")[0]["status"] == "published"
    assert rows(conn, "SELECT * FROM incident_log WHERE kind = 'trigger'") == []


def test_spiked_batch_fires_and_holds_the_whole_import(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    for i in range(20):
        seed_published(conn, f"hist-{i}.csv", 0.50 + (0.01 if i % 2 else -0.01), i)
    seed_pending(conn, "today.csv", 0.95, n=3)  # a wild spike
    result = decide_and_act(ctx_for(conn, "today.csv"))
    assert result["fired"] is True and result["action"] == "hold_and_alert"
    statuses = {r["status"] for r in rows(conn, "SELECT status FROM silver_records WHERE file_name='today.csv'")}
    assert statuses == {"held"}
    incidents = rows(conn, "SELECT * FROM incident_log WHERE kind = 'trigger'")
    assert len(incidents) == 1 and "today.csv" in incidents[0]["detail"]
    dec = rows(conn, "SELECT * FROM decision_log WHERE file_name = 'today.csv'")[0]
    assert dec["fired"] == 1 and abs(dec["statistic"]) > Z_THRESHOLD


def test_no_pending_records_is_a_no_op(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    result = decide_and_act(ctx_for(conn, "empty.csv"))
    assert result == {"fired": False, "action": "none", "n": 0}
    assert rows(conn, "SELECT * FROM decision_log WHERE file_name = 'empty.csv'") == []


def test_only_the_last_60_published_imports_count(tmp_path):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    for i in range(40):  # older than the 60-import window: must be excluded
        seed_published(conn, f"old-{i}.csv", 0.10, i)
    for i in range(40, 100):  # the most recent 60: exactly fills the window
        seed_published(conn, f"recent-{i}.csv", 0.50 + (0.01 if i % 2 else -0.01), i)
    seed_pending(conn, "today.csv", 0.51)
    result = decide_and_act(ctx_for(conn, "today.csv"))
    assert result["fired"] is False  # if the stale 0.10 imports leaked into the window, this would fire
