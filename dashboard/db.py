"""Read-only access to the agent's SQLite database.

Only the agent writes; the dashboard opens the file read-only (references/dashboard.md),
except for agent/release.py's Release/Reject action, which is the one human-decision
exception the project allows locally. In the cloud (milestone 6) that action moves to a
GitHub Actions workflow_dispatch call instead of writing to the file directly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agent.config import load_agent_config


def read_only_connection(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def writable_connection(path: Path) -> sqlite3.Connection:
    """Only for agent/release.py's human Release/Reject action."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def sqlite_path() -> Path:
    return load_agent_config()["sqlite_path"]


def rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def latest_run(conn: sqlite3.Connection) -> dict | None:
    r = rows(conn, "SELECT run_id, file_name, MAX(started_at) AS started_at FROM run_log "
                   "GROUP BY run_id ORDER BY started_at DESC LIMIT 1")
    return r[0] if r else None


def run_log_for(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    return rows(conn, "SELECT * FROM run_log WHERE run_id = ? ORDER BY started_at", (run_id,))


def sql_log_for(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    return rows(conn, "SELECT * FROM sql_log WHERE run_id = ? ORDER BY executed_at", (run_id,))


def model_usage_for(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    return rows(conn, "SELECT * FROM model_usage_log WHERE run_id = ? ORDER BY called_at", (run_id,))


def decision_for(conn: sqlite3.Connection, run_id: str) -> dict | None:
    r = rows(conn, "SELECT * FROM decision_log WHERE run_id = ?", (run_id,))
    return r[0] if r else None


def open_trigger_holds(conn: sqlite3.Connection) -> list[dict]:
    """Every currently-held import (fired trigger, not yet released or rejected),
    most recent first, with how many rows are waiting."""
    return rows(conn,
                "SELECT i.run_id, rl.file_name, i.incident_id, i.detail, i.opened_at, "
                "       (SELECT COUNT(*) FROM silver_records sr "
                "        WHERE sr.file_name = rl.file_name AND sr.status = 'held' AND sr.consistency_ok = 1) AS n_held "
                "FROM incident_log i JOIN run_log rl ON rl.run_id = i.run_id "
                "WHERE i.kind = 'trigger' AND i.status = 'open' "
                "GROUP BY i.incident_id ORDER BY i.opened_at DESC")


def recent_run_ids(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    return rows(conn, "SELECT run_id, file_name, MIN(started_at) AS started_at, "
                      "MAX(finished_at) AS finished_at FROM run_log "
                      "GROUP BY run_id ORDER BY started_at DESC LIMIT ?", (limit,))


def run_log_rows_for_runs(conn: sqlite3.Connection, run_ids: list[str]) -> list[dict]:
    if not run_ids:
        return []
    placeholders = ",".join("?" for _ in run_ids)
    return rows(conn, f"SELECT * FROM run_log WHERE run_id IN ({placeholders})", tuple(run_ids))


# ---------------------------------------------------------------- Data page

def silver_records(conn: sqlite3.Connection, status: str | None = None, school_code: str | None = None,
                   grad_year: int | None = None, limit: int = 5000) -> list[dict]:
    where, params = [], []
    if status is not None:
        where.append("status = ?")
        params.append(status)
    if school_code is not None:
        where.append("school_code = ?")
        params.append(school_code)
    if grad_year is not None:
        where.append("grad_year = ?")
        params.append(grad_year)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)
    return rows(conn, f"SELECT * FROM silver_records {clause} ORDER BY landed_at DESC LIMIT ?", tuple(params))


def distinct_statuses(conn: sqlite3.Connection) -> list[str]:
    return [r["status"] for r in rows(conn, "SELECT DISTINCT status FROM silver_records ORDER BY status")]


def distinct_school_codes(conn: sqlite3.Connection) -> list[str]:
    return [r["school_code"] for r in rows(
        conn, "SELECT DISTINCT school_code FROM silver_records WHERE school_code IS NOT NULL ORDER BY school_code")]


def distinct_grad_years(conn: sqlite3.Connection) -> list[int]:
    return [r["grad_year"] for r in rows(
        conn, "SELECT DISTINCT grad_year FROM silver_records WHERE grad_year IS NOT NULL ORDER BY grad_year")]


def imports_per_minute(conn: sqlite3.Connection, limit_minutes: int = 60) -> list[dict]:
    """One row per calendar minute, from the Detect step's own timestamps -- not
    generator_log.csv, which the agent never reads as input."""
    return rows(conn, "SELECT substr(started_at, 1, 16) AS minute, COUNT(*) AS n FROM run_log "
                      "WHERE step = 'detect' AND status = 'ok' GROUP BY minute ORDER BY minute DESC LIMIT ?",
               (limit_minutes,))
