"""Milestone 6: the daily summary a Claude Routine (or its GitHub Actions fallback) reads
(references/cloud.md). Written after each minute's import in the cloud loop, and runnable
standalone locally. A plain aggregation of the log tables that already exist -- no model call.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agent.sql import now_iso


def daily_summary(conn: sqlite3.Connection) -> dict:
    today = now_iso()[:10]

    def rows(sql: str, params: tuple = ()) -> list[dict]:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    imports_today = rows("SELECT COUNT(DISTINCT file_name) AS n FROM run_log WHERE step = 'land' "
                        "AND substr(started_at, 1, 10) = ?", (today,))[0]["n"]
    held = rows("SELECT file_name, COUNT(*) AS n_held FROM silver_records WHERE status = 'held' "
               "GROUP BY file_name ORDER BY file_name")
    incidents_open = rows("SELECT incident_id, kind, detail, opened_at FROM incident_log "
                          "WHERE status = 'open' ORDER BY opened_at DESC LIMIT 50")
    usage_today = rows("SELECT expert, COUNT(*) AS calls, SUM(input_tokens + output_tokens) AS tokens, "
                      "SUM(estimated_cost_usd) AS cost_usd FROM model_usage_log "
                      "WHERE substr(called_at, 1, 10) = ? GROUP BY expert", (today,))
    latest_published = rows("SELECT file_name, AVG(emp_rate) AS mean_rate FROM silver_records "
                           "WHERE status = 'published' AND emp_rate IS NOT NULL "
                           "GROUP BY file_name ORDER BY landed_at DESC LIMIT 1")
    # Anything that might break the AI use policy's "a person releases every held import" rule
    # or otherwise needs a human's attention beyond the ordinary held-import flow.
    policy_flags = rows("SELECT incident_id, kind, detail FROM incident_log "
                       "WHERE kind IN ('injection', 'failure') AND status = 'open'")

    return {
        "generated_at": now_iso(),
        "imports_processed_today": imports_today,
        "held_imports": held,
        "incidents_open": incidents_open,
        "model_usage_by_expert_today": usage_today,
        "latest_published_batch": latest_published[0] if latest_published else None,
        "ai_use_policy_flags": policy_flags,
    }


def write_daily_summary(conn: sqlite3.Connection, path: Path) -> dict:
    summary = daily_summary(conn)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary
