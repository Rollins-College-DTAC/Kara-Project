"""SQLite connection and the tables milestone 2 needs.

The other log tables (model_usage_log, stats_log, decision_log) arrive with the
milestones that write to them.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS run_log (
        run_id TEXT, step TEXT,          -- detect, land, route, classify, extract, validate, load, decide, act
        file_name TEXT, file_sha256 TEXT,
        started_at TEXT, finished_at TEXT,
        rows_in INTEGER, rows_out INTEGER, rows_rejected INTEGER,
        status TEXT,                     -- running, ok, warning, held, failed
        message TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS sql_log (
        run_id TEXT, step TEXT, file_name TEXT,
        sql_text TEXT,                   -- statement with ? placeholders
        params_json TEXT,                -- values, long text shortened
        rows_affected INTEGER, duration_ms INTEGER, executed_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS incident_log (
        incident_id TEXT, run_id TEXT, kind TEXT,   -- trigger, injection, budget, failure
        detail TEXT, status TEXT,                   -- open, released, rejected
        decided_by TEXT, opened_at TEXT, closed_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS file_registry (
        sha256 TEXT PRIMARY KEY,         -- one row per distinct file content ever seen
        file_name TEXT, size_bytes INTEGER,
        first_seen_at TEXT, run_id TEXT,
        status TEXT,                     -- detected, landed, quarantined
        rows_landed INTEGER
    )""",
]


def connect(path: Path) -> sqlite3.Connection:
    """Open the database in WAL mode (the agent writes, the dashboard only reads)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    for ddl in SCHEMA:
        conn.execute(ddl)
    conn.commit()
    return conn
