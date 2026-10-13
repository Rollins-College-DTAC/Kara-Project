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
    # ---- milestone 3: expert models
    """CREATE TABLE IF NOT EXISTS model_usage_log (
        call_id TEXT, run_id TEXT, step TEXT,
        task TEXT,                       -- classify, extract, escalate, explain, report
        expert TEXT,                     -- jev, claude-haiku-4-5, claude-sonnet-5-5, rules
        route_reason TEXT,               -- why the router chose this expert
        prompt_version TEXT,
        input_tokens INTEGER, output_tokens INTEGER, latency_ms INTEGER,
        confidence REAL, estimated_cost_usd REAL,
        pii_redacted INTEGER, outcome TEXT,   -- valid, retried, escalated, quarantined, failed
        called_at TEXT,
        file_name TEXT, row_index INTEGER, cached INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS model_cache (
        cache_key TEXT PRIMARY KEY,      -- sha256 of expert, model, task, prompt version and input text
        expert TEXT, task TEXT, prompt_version TEXT,
        response_json TEXT, created_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS record_status (
        file_name TEXT, row_index INTEGER, run_id TEXT,
        has_notes INTEGER, pii_redacted INTEGER,
        category TEXT, category_confidence REAL, urgency TEXT, injection_probability REAL,
        classify_expert TEXT, extract_expert TEXT, extraction_json TEXT,
        status TEXT,                     -- no_notes, extracted, review, quarantined
        reason TEXT, updated_at TEXT,
        PRIMARY KEY (file_name, row_index)
    )""",
    """CREATE TABLE IF NOT EXISTS review_queue (
        review_id TEXT PRIMARY KEY, run_id TEXT, file_name TEXT, row_index INTEGER,
        reason TEXT, status TEXT,        -- open, approved, rejected
        decided_by TEXT, opened_at TEXT, closed_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS eval_log (
        eval_id TEXT, evaluated_at TEXT, expert TEXT, metric TEXT,
        value REAL, threshold REAL, passed INTEGER,
        questions_version TEXT, prompt_version TEXT, n_records INTEGER
    )""",
    # ---- milestone 4: Load (clean, typed, consistency-checked)
    """CREATE TABLE IF NOT EXISTS silver_records (
        file_name TEXT, row_index INTEGER, run_id TEXT,
        school_code TEXT,                -- canonical 'LS-01'..'LS-30', or NULL if unrecognized
        school_name TEXT,                -- canonical name from generator/schools.json
        school_name_raw TEXT,            -- the import's own (possibly messy) name, kept for audit
        grad_year INTEGER, report_date TEXT,     -- ISO YYYY-MM-DD
        class_size INTEGER, grads INTEGER,
        acceptance_rate REAL,            -- fraction 0-1
        lsat_25 INTEGER, lsat_50 INTEGER, lsat_75 INTEGER,
        gpa_25 REAL, gpa_50 REAL, gpa_75 REAL,
        scholarship_share REAL,          -- fraction 0-1
        emp_bar_required INTEGER, emp_jd_advantage INTEGER, emp_other INTEGER, emp_unemployed INTEGER,
        emp_rate REAL,                   -- emp_bar_required / grads: the forecast measure
        bar_pass_rate REAL,              -- fraction 0-1
        consistency_ok INTEGER, consistency_flags TEXT,   -- JSON list of broken rule names
        status TEXT,                     -- held (consistency failed), pending (awaiting the batch trigger), published
        landed_at TEXT,
        PRIMARY KEY (file_name, row_index)
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
