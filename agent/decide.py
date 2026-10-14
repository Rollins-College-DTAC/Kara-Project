"""Steps 8-9, Decide and Act: the anomaly trigger (milestone 4 stage 3).

Decide: z-score of this import's mean employment rate (emp_rate, from Load) against the
batch means of the last 60 published imports (references/statistics.md: fires when the
absolute z is above 3). Needs at least MIN_HISTORY prior published imports before a z-score
means anything; before that, every import auto-publishes (matching the generator's own
warmup_imports, which never seeds an anomaly in the first few imports either).

Act: not fired -> publish every consistent (status='pending') row in this import to the
gold view. Fired -> hold the whole import (even rows that passed their own consistency
checks), open a 'trigger' incident, and wait for a person to release it. The agent never
publishes a held import on its own -- same rule as the consistency checks in Load.

Rolling history comes straight from silver_records (grouping published rows by file_name),
so there's no separate table to keep in sync with it.
"""

from __future__ import annotations

import statistics

from agent.sql import RunContext, now_iso, open_incident, run_sql, step

WINDOW = 60
Z_THRESHOLD = 3.0
MIN_HISTORY = 5


def recent_batch_means(ctx: RunContext, exclude_file: str, window: int = WINDOW) -> list[float]:
    rows = run_sql(ctx, "decide",
                   "SELECT file_name, AVG(emp_rate) AS mean_rate, MAX(landed_at) AS landed_at "
                   "FROM silver_records WHERE status = 'published' AND consistency_ok = 1 "
                   "AND emp_rate IS NOT NULL AND file_name != ? "
                   "GROUP BY file_name ORDER BY landed_at DESC LIMIT ?",
                   (exclude_file, window)).fetchall()
    return [r["mean_rate"] for r in rows]


def decide_and_act(ctx: RunContext) -> dict:
    with step(ctx, "decide") as s:
        rows = run_sql(ctx, "decide",
                       "SELECT emp_rate FROM silver_records WHERE file_name = ? AND status = 'pending' "
                       "AND emp_rate IS NOT NULL", (ctx.file_name,)).fetchall()
        rates = [r["emp_rate"] for r in rows]
        if not rates:
            s.message = "no pending records with an employment rate: nothing to decide"
            return {"fired": False, "action": "none", "n": 0}

        batch_mean = statistics.fmean(rates)
        history = recent_batch_means(ctx, ctx.file_name)
        z = None
        if len(history) < MIN_HISTORY:
            fired = False
            detail = f"only {len(history)} published imports so far (need {MIN_HISTORY}): auto-publish"
        else:
            mu, sigma = statistics.fmean(history), statistics.pstdev(history)
            z = (batch_mean - mu) / sigma if sigma else 0.0
            fired = abs(z) > Z_THRESHOLD
            detail = f"z={z:.2f} against {len(history)} prior imports (mean {mu:.3f}, sd {sigma:.4f})"

        action = "hold_and_alert" if fired else "publish"
        run_sql(ctx, "decide",
                "INSERT INTO decision_log (run_id, file_name, rule, statistic, threshold, p_value, fired, "
                "action, detail, decided_at) VALUES (?, ?, 'anomaly', ?, ?, NULL, ?, ?, ?, ?)",
                (ctx.run_id, ctx.file_name, z, Z_THRESHOLD, int(fired), action, detail, now_iso()))

        s.rows_in = len(rates)
        s.status = "held" if fired else "ok"
        s.message = f"batch mean {batch_mean:.3f}; {detail}; {'FIRED' if fired else 'not fired'}"

    with step(ctx, "act") as s:
        if fired:
            open_incident(ctx, "trigger",
                          f"{ctx.file_name}: anomaly trigger fired ({detail}); import held, waiting for release")
        run_sql(ctx, "act",
                "UPDATE silver_records SET status = ? WHERE file_name = ? AND status = 'pending'",
                ("held" if fired else "published", ctx.file_name))
        s.rows_in = s.rows_out = len(rates)
        s.message = f"{len(rates)} records -> {action}"

    return {"fired": fired, "action": action, "n": len(rates), "z": z, "batch_mean": batch_mean}
