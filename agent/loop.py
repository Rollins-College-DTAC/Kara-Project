"""The ETL loop (milestone 2 covers Detect and Land).

Run continuously:   python -m agent.loop
Scan once and exit: python -m agent.loop --once      (this is what GitHub Actions will use)

Every file gets its own run ID. Each step writes a run_log row when it starts and
finishes, and every query goes through run_sql() into sql_log.
"""

from __future__ import annotations

import argparse
import logging
import time
from contextlib import closing
from pathlib import Path

from agent.config import load_agent_config
from agent.db import connect
from agent.detect import detect
from agent.land import ParseError, land_records, move_unique, parse_file
from agent.sql import RunContext, new_run_id, open_incident, run_sql, step

log = logging.getLogger("agent")


def _where(cfg: dict, dest: Path) -> str:
    """Short, readable location like 'processed/duplicates/file.csv'."""
    try:
        return str(dest.relative_to(cfg["processed"].parent))
    except ValueError:
        return str(dest)


def process_file(cfg: dict, conn, path: Path) -> str:
    """Detect and land one file. Returns 'landed', 'duplicate' or 'quarantined'."""
    ctx = RunContext(conn=conn, run_id=new_run_id(), file_name=path.name)
    try:
        # 1. Detect: hash, and skip content we have already seen.
        with step(ctx, "detect") as s:
            found = detect(ctx, path)
            s.rows_in = 1
            if found.duplicate_of:
                dest = move_unique(path, cfg["processed"] / "duplicates")
                s.status = "warning"
                s.rows_out = 0
                s.message = (f"skipped: same SHA-256 as {found.duplicate_of} ({found.sha256[:12]}...); "
                             f"moved to {_where(cfg, dest)}")
            else:
                s.rows_out = 1
                s.message = f"new file, {found.size_bytes} bytes, sha256 {found.sha256[:12]}..."
        if found.duplicate_of:
            log.info("Skipped %s (duplicate of %s)", path.name, found.duplicate_of)
            return "duplicate"

        # 2. Land: raw records into TinyDB, then move the file out of the inbox.
        with step(ctx, "land") as s:
            records = parse_file(path)
            s.rows_in = len(records)
            s.rows_out = land_records(ctx, cfg["raw_path"], records)
            dest = move_unique(path, cfg["processed"])
            run_sql(ctx, "land",
                    "UPDATE file_registry SET status = ?, rows_landed = ? WHERE sha256 = ?",
                    ("landed", s.rows_out, ctx.file_sha256))
            s.message = f"landed {s.rows_out} records in raw.json; moved to {_where(cfg, dest)}"
        log.info("Landed %s (%d records)", path.name, s.rows_out)
        return "landed"

    except Exception as exc:  # the failed step is already in run_log
        return _quarantine(cfg, ctx, path, exc)


def _quarantine(cfg: dict, ctx: RunContext, path: Path, exc: Exception) -> str:
    """A file we could not land goes to quarantine/ and a person is told via incident_log."""
    where = "(file not found)"
    if path.exists():
        where = _where(cfg, move_unique(path, cfg["quarantine"]))
    if ctx.file_sha256:
        run_sql(ctx, "land", "UPDATE file_registry SET status = ? WHERE sha256 = ?",
                ("quarantined", ctx.file_sha256))
    kind = "failure"
    open_incident(ctx, kind, f"{path.name}: {type(exc).__name__}: {exc}; moved to {where}")
    log.warning("Quarantined %s: %s", path.name, exc)
    return "quarantined"


def scan_once(cfg: dict) -> list[tuple[str, str]]:
    """Process every settled file in the inbox, oldest first. Returns (file name, outcome) pairs."""
    inbox = cfg["inbox"]
    if not inbox.exists():
        return []
    cutoff = time.time() - cfg.get("settle_seconds", 0)
    # Skip files still being written (modified within the settle window).
    files = sorted((p for p in inbox.iterdir() if p.is_file() and p.stat().st_mtime <= cutoff),
                   key=lambda p: (p.stat().st_mtime, p.name))
    results = []
    with closing(connect(cfg["sqlite_path"])) as conn:
        for path in files:
            results.append((path.name, process_file(cfg, conn, path)))
    return results


def main() -> None:
    cfg = load_agent_config()
    p = argparse.ArgumentParser(description="Watch the inbox and run Detect and Land on each new file.")
    p.add_argument("--once", action="store_true", help="scan once and exit")
    p.add_argument("--scan-seconds", type=float, default=cfg["scan_seconds"])
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    if args.once:
        scan_once(cfg)
        return

    # APScheduler polls the inbox: file-change events do not reach Docker containers on Windows or macOS.
    from datetime import datetime
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()
    scheduler.add_job(scan_once, "interval", seconds=args.scan_seconds, args=[cfg],
                      max_instances=1, coalesce=True, next_run_time=datetime.now())
    log.info("Watching %s every %ss (Ctrl+C to stop)", cfg["inbox"], args.scan_seconds)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
