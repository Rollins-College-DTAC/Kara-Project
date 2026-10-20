"""Compute the three statistics (Wilson CI, two-proportion test, correlation/regression) over
every published silver_records row so far, and log each to stats_log.

This is a standing analytics pass over the gold data (references/requirements.md: "Analytics
(gold)... published imports only"), not a per-import step like the anomaly trigger (stage 3) is.
Run it whenever you want the dashboard's Analytics page numbers refreshed.

Usage:
  python scripts/compute_stats.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import load_agent_config  # noqa: E402
from agent.db import connect  # noqa: E402
from agent.sql import RunContext, new_run_id, now_iso, run_sql  # noqa: E402
from agent.stats import compute_all  # noqa: E402


def run(cfg: dict) -> list[dict]:
    conn = connect(cfg["sqlite_path"])
    ctx = RunContext(conn=conn, run_id=new_run_id(), file_name="stats:aggregate")
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM silver_records WHERE status = 'published'").fetchall()]
    results = compute_all(rows)
    for stat in results:
        extra = {k: v for k, v in stat.items()
                 if k not in ("method", "formula_latex", "inputs", "result", "threshold", "interpretation")}
        run_sql(ctx, "stats",
                "INSERT INTO stats_log (run_id, step, method, formula_latex, inputs_json, result, threshold, "
                "interpretation, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ctx.run_id, "stats", stat["method"], stat["formula_latex"],
                 json.dumps({**stat["inputs"], **extra}), stat["result"], stat.get("threshold"),
                 stat["interpretation"], now_iso()))
    conn.close()
    return results


def main() -> None:
    cfg = load_agent_config()
    results = run(cfg)
    if not results:
        print("No consistent silver_records yet (run the generator and agent loop first).")
        return
    for r in results:
        print(f"\n{r['method']}")
        print(" ", r["interpretation"])
    print(f"\n{len(results)} statistics logged to stats_log.")


if __name__ == "__main__":
    main()
