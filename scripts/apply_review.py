"""Milestone 6: applies a human Release/Reject decision from the cloud dashboard.

Called by .github/workflows/review.yml (workflow_dispatch: incident_id, decision, reviewer).
Looks up the held import from its incident, applies agent.release's release/reject (the same
logic the local dashboard uses directly), then commits and pushes the data branch -- in the
cloud, the dashboard itself never writes the database file; it only starts this workflow
(references/dashboard.md).

Usage:
  uv run python scripts/apply_review.py --state state/ --incident-id inc-xxx \
      --decision release --reviewer KB
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.cloud_loop import commit_and_push_data_branch  # noqa: E402
from agent.release import reject_import, release_import  # noqa: E402
from dashboard.db import writable_connection  # noqa: E402


def file_name_for_incident(conn: sqlite3.Connection, incident_id: str) -> str:
    row = conn.execute(
        "SELECT rl.file_name FROM incident_log i JOIN run_log rl ON rl.run_id = i.run_id "
        "WHERE i.incident_id = ? AND i.kind = 'trigger'", (incident_id,)).fetchone()
    if not row:
        raise SystemExit(f"no open trigger incident found for incident_id {incident_id!r}")
    return row["file_name"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--incident-id", required=True)
    p.add_argument("--decision", choices=["release", "reject"], required=True)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--no-push", action="store_true", help="for local testing: skip git commit/push")
    args = p.parse_args()

    conn = writable_connection(args.state / "data" / "analytics.sqlite")
    file_name = file_name_for_incident(conn, args.incident_id)
    apply_decision = release_import if args.decision == "release" else reject_import
    n = apply_decision(conn, file_name, args.reviewer)
    conn.close()
    verb = {"release": "released", "reject": "rejected"}[args.decision]
    print(f"{verb} {file_name}: {n} rows")

    if not args.no_push:
        pushed = commit_and_push_data_branch(args.state)
        print(f"pushed data branch: {pushed}")


if __name__ == "__main__":
    main()
