"""Print recent run_log and sql_log rows, so every step is visible before the dashboard exists.

Usage: python scripts/show_log.py [--db data/analytics.sqlite] [--limit 20] [--file NAME]
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def table(rows: list[sqlite3.Row], columns: list[tuple[str, int]]) -> None:
    print("  ".join(name.ljust(width) for name, width in columns))
    print("  ".join("-" * width for _, width in columns))
    for row in rows:
        print("  ".join(str(row[name] if row[name] is not None else "")[:width].ljust(width) for name, width in columns))
    print()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/analytics.sqlite")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--file", help="only rows for this file name")
    args = p.parse_args()

    if not Path(args.db).exists():
        raise SystemExit(f"No database at {args.db}. Run the agent first.")
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    where, params = ("WHERE file_name = ?", (args.file,)) if args.file else ("", ())

    print("run_log (newest first)")
    rows = conn.execute(
        f"SELECT step, status, file_name, rows_in, rows_out, message FROM run_log {where} "
        "ORDER BY started_at DESC, rowid DESC LIMIT ?", (*params, args.limit)).fetchall()
    table(rows, [("step", 7), ("status", 8), ("file_name", 46), ("rows_in", 7), ("rows_out", 8), ("message", 90)])

    print("sql_log (newest first)")
    rows = conn.execute(
        f"SELECT step, file_name, sql_text, params_json FROM sql_log {where} "
        "ORDER BY executed_at DESC, rowid DESC LIMIT ?", (*params, args.limit)).fetchall()
    table(rows, [("step", 7), ("file_name", 46), ("sql_text", 70), ("params_json", 50)])

    print("incident_log")
    rows = conn.execute("SELECT incident_id, kind, status, detail FROM incident_log ORDER BY opened_at DESC LIMIT ?",
                        (args.limit,)).fetchall()
    table(rows, [("incident_id", 12), ("kind", 8), ("status", 7), ("detail", 100)])


if __name__ == "__main__":
    main()
