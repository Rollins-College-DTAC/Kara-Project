"""Logging helpers: run_sql() for every query, step() for every run_log row.

Two rules from the project:
- Every query goes through run_sql(), which logs it to sql_log with the file name.
  Values are always passed separately with ? placeholders, never pasted into SQL text.
- The helper's own writes to the log tables are not themselves logged.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

MAX_LOGGED_TEXT = 80  # long text values are shortened in sql_log


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_run_id() -> str:
    return f"run-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


@dataclass
class RunContext:
    """What one pass over one file carries along."""
    conn: sqlite3.Connection
    run_id: str
    file_name: str
    file_sha256: str = ""


@dataclass
class StepResult:
    """Fill these in inside a `with step(...)` block; they are written to run_log on exit."""
    rows_in: int | None = None
    rows_out: int | None = None
    rows_rejected: int | None = None
    status: str = "ok"          # ok, warning, held, failed
    message: str = ""
    extra: dict = field(default_factory=dict)


def _shorten(value):
    if isinstance(value, str) and len(value) > MAX_LOGGED_TEXT:
        return f"{value[:MAX_LOGGED_TEXT]}...(+{len(value) - MAX_LOGGED_TEXT} chars)"
    return value


def run_sql(ctx: RunContext, step_name: str, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
    """Run one statement, then record it in sql_log."""
    started = time.perf_counter()
    cur = ctx.conn.execute(sql, tuple(params))
    ctx.conn.commit()
    duration_ms = int((time.perf_counter() - started) * 1000)
    # This INSERT is the logger's own write, so it is not logged again.
    ctx.conn.execute(
        "INSERT INTO sql_log (run_id, step, file_name, sql_text, params_json, rows_affected, duration_ms, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ctx.run_id, step_name, ctx.file_name, " ".join(sql.split()),
         json.dumps([_shorten(p) for p in params], default=str),
         cur.rowcount if cur.rowcount >= 0 else None, duration_ms, now_iso()),
    )
    ctx.conn.commit()
    return cur


@contextmanager
def step(ctx: RunContext, name: str):
    """Write a run_log row when the step starts and finish it when the block ends."""
    result = StepResult()
    rowid = ctx.conn.execute(
        "INSERT INTO run_log (run_id, step, file_name, file_sha256, started_at, status) VALUES (?, ?, ?, ?, ?, 'running')",
        (ctx.run_id, name, ctx.file_name, ctx.file_sha256, now_iso()),
    ).lastrowid
    ctx.conn.commit()

    def finish(status: str, message: str) -> None:
        ctx.conn.execute(
            "UPDATE run_log SET file_sha256 = ?, finished_at = ?, rows_in = ?, rows_out = ?, rows_rejected = ?, "
            "status = ?, message = ? WHERE rowid = ?",
            (ctx.file_sha256, now_iso(), result.rows_in, result.rows_out, result.rows_rejected, status, message, rowid),
        )
        ctx.conn.commit()

    try:
        yield result
    except Exception as exc:
        finish("failed", f"{type(exc).__name__}: {exc}")
        raise
    else:
        finish(result.status, result.message)


def open_incident(ctx: RunContext, kind: str, detail: str) -> str:
    """Record something a person needs to look at (written directly, like the other log tables)."""
    incident_id = f"inc-{uuid.uuid4().hex[:8]}"
    ctx.conn.execute(
        "INSERT INTO incident_log (incident_id, run_id, kind, detail, status, opened_at) VALUES (?, ?, ?, ?, 'open', ?)",
        (incident_id, ctx.run_id, kind, detail[:400], now_iso()),
    )
    ctx.conn.commit()
    return incident_id
