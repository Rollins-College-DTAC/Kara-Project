"""A person releases or rejects a trigger-held import, from the dashboard's alert banner.

Only rows held because the whole import's trigger fired are affected here (status='held'
AND consistency_ok=1) -- a row that failed its own consistency check (stage 1) needs separate
attention and is left alone, since "the import looked fine except this one broken row" is a
different problem than "the whole batch looks anomalous".

Locally this writes straight to SQLite, the one exception to "only the agent writes" the
project allows for a human decision. In the cloud (milestone 6), this moves to a GitHub
Actions workflow_dispatch call instead (references/dashboard.md, references/cloud.md).
"""

from __future__ import annotations

from agent.sql import RunContext, new_run_id, now_iso, run_sql, step


def _resolve(conn, file_name: str, decided_by: str, new_status: str, incident_status: str) -> int:
    if not decided_by.strip():
        raise ValueError("decided_by is required: a person releases every held import")
    ctx = RunContext(conn=conn, run_id=new_run_id(), file_name=file_name)
    with step(ctx, "act") as s:
        cur = run_sql(ctx, "act",
                      "UPDATE silver_records SET status = ? WHERE file_name = ? AND status = 'held' "
                      "AND consistency_ok = 1", (new_status, file_name))
        n = cur.rowcount
        run_sql(ctx, "act",
                "UPDATE incident_log SET status = ?, decided_by = ?, closed_at = ? "
                "WHERE kind = 'trigger' AND status = 'open' "
                "AND run_id IN (SELECT run_id FROM run_log WHERE file_name = ?)",
                (incident_status, decided_by, now_iso(), file_name))
        s.rows_out = n
        s.message = f"{incident_status} by {decided_by}: {n} rows -> {new_status}"
    return n


def release_import(conn, file_name: str, decided_by: str) -> int:
    """Publish the rows a fired trigger held."""
    return _resolve(conn, file_name, decided_by, "published", "released")


def reject_import(conn, file_name: str, decided_by: str) -> int:
    """Exclude the rows a fired trigger held; they never reach the gold view."""
    return _resolve(conn, file_name, decided_by, "rejected", "rejected")
