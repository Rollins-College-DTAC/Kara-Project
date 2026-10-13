"""Step 7, Load: clean each record's structured fields into the silver layer (SQLite).

Runs after Validate (milestone 3), independent of it: Load cleans the record's own
admissions/employment/bar-passage columns, not Claude's extraction from the notes field.
A record that fails a consistency check is held, never published, and opens an incident
for a person to look at (the project's rule: a person releases every held import). A
record that passes stays "pending" until the batch-level anomaly trigger decides the
whole import (milestone 4, Decide and Act).
"""

from __future__ import annotations

import json

from agent.clean import clean_record
from agent.sql import RunContext, now_iso, open_incident, run_sql, step


def load_records(ctx: RunContext, records: list[dict]) -> dict:
    with step(ctx, "load") as s:
        held = 0
        for i, raw in enumerate(records):
            c = clean_record(raw)
            status = "held" if not c["consistency_ok"] else "pending"
            if not c["consistency_ok"]:
                held += 1
                open_incident(ctx, "consistency",
                              f"{ctx.file_name} row {i}: broke {', '.join(c['consistency_flags'])}")
            run_sql(ctx, "load",
                    "INSERT OR REPLACE INTO silver_records (file_name, row_index, run_id, school_code, "
                    "school_name, school_name_raw, grad_year, report_date, class_size, grads, acceptance_rate, "
                    "lsat_25, lsat_50, lsat_75, gpa_25, gpa_50, gpa_75, scholarship_share, emp_bar_required, "
                    "emp_jd_advantage, emp_other, emp_unemployed, emp_rate, bar_pass_rate, consistency_ok, "
                    "consistency_flags, status, landed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (ctx.file_name, i, ctx.run_id, c["school_code"], c["school_name"], c["school_name_raw"],
                     c["grad_year"], c["report_date"], c["class_size"], c["grads"], c["acceptance_rate"],
                     c["lsat_25"], c["lsat_50"], c["lsat_75"], c["gpa_25"], c["gpa_50"], c["gpa_75"],
                     c["scholarship_share"], c["emp_bar_required"], c["emp_jd_advantage"], c["emp_other"],
                     c["emp_unemployed"], c["emp_rate"], c["bar_pass_rate"], int(c["consistency_ok"]),
                     json.dumps(c["consistency_flags"]), status, now_iso()))
        s.rows_in = len(records)
        s.rows_out = len(records) - held
        s.rows_rejected = held
        s.status = "warning" if held else "ok"
        s.message = f"{held} held for a broken consistency rule" if held else "all records consistent"
        return {"loaded": len(records) - held, "held": held}
