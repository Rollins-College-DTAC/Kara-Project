"""Loads real ABA school profiles into the school_profile table. Every insert goes through
run_sql, so each one is visible in sql_log with its parameters, and the step is in run_log."""

from __future__ import annotations

import json

from agent.sql import RunContext, now_iso, run_sql, step

COLUMNS = [
    "school_key", "school_name", "school_type", "basics_edition", "admissions_edition", "cost_edition",
    "grants_edition", "bar_edition", "bar_two_year_edition", "applications", "offers", "acceptance_rate",
    "enrollees", "lsat_25", "lsat_50", "lsat_75", "gpa_25", "gpa_50", "gpa_75", "tuition_resident",
    "tuition_nonresident", "tuition_basis", "fees", "living_off_campus", "grants_share", "grant_median_ft",
    "full_tuition_share", "est_net_tuition", "bar_first_time_takers", "bar_first_time_pass", "bar_state_avg",
    "bar_two_year_pass",
]
SQL = (f"INSERT OR REPLACE INTO school_profile ({', '.join(COLUMNS)}, consistency_ok, consistency_flags, loaded_at) "
       f"VALUES ({', '.join('?' * (len(COLUMNS) + 3))})")


def load_profiles(ctx: RunContext, profiles: list[dict]) -> dict:
    with step(ctx, "profile") as s:
        bad = 0
        for p in profiles:
            ok = not p["flags"]
            bad += not ok
            run_sql(ctx, "profile", SQL, [p.get(c) for c in COLUMNS] + [int(ok), json.dumps(p["flags"]), now_iso()])
        s.rows_in, s.rows_out, s.rows_rejected = len(profiles), len(profiles) - bad, bad
        s.status = "warning" if bad else "ok"
        s.message = f"{len(profiles)} real school profiles; {bad} flagged by a sanity rule"
    return {"loaded": len(profiles), "flagged": bad}
