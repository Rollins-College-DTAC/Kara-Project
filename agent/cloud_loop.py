"""Milestone 6: runs the whole pipeline once a minute, N times, inside one GitHub Actions job
(references/cloud.md: GitHub Actions schedules can't run more often than every 5 minutes and
can start late or be skipped, so the per-minute cadence lives inside one job instead of a cron
schedule). Reuses the exact same pipeline code as local mode -- generator, agent.loop,
scripts.compute_stats -- so only the paths (everything under --state) and the final
commit-to-the-data-branch step differ.

The .github/workflows/pipeline.yml workflow checks out the `data` branch into --state before
calling this; this module assumes that worktree already exists and only commits and pushes it.

Usage (meant to run inside the workflow, but behaves the same locally against any git
worktree, including a throwaway one for testing):
  uv run python -m agent.cloud_loop --minutes 30 --state state/
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import time
from pathlib import Path

from agent.config import load_agent_config
from agent.db import connect
from agent.export import write_daily_summary
from agent.loop import scan_once
from generator import generate as g
from scripts.compute_stats import run as run_stats

log = logging.getLogger("cloud_loop")


def _state_cfg(cfg: dict, state: Path) -> dict:
    cfg = dict(cfg)
    cfg["inbox"], cfg["processed"], cfg["quarantine"] = state / "inbox", state / "processed", state / "quarantine"
    cfg["data_dir"] = state / "data"
    cfg["sqlite_path"] = cfg["data_dir"] / "analytics.sqlite"
    cfg["raw_path"] = cfg["data_dir"] / "raw.json"
    return cfg


def process_and_export(cfg: dict, state: Path) -> dict:
    """One minute's worth of work after the generator has written its import: ETL, stats,
    the daily summary export. Returns the summary for logging."""
    scan_once(cfg)
    run_stats(cfg)
    conn = connect(cfg["sqlite_path"])
    try:
        return write_daily_summary(conn, state / "exports" / "daily_summary.json")
    finally:
        conn.close()


def commit_and_push_data_branch(state: Path) -> bool:
    """Amend the data branch's one commit and force-push it (references/cloud.md: this keeps
    the branch one commit deep; the real history lives in the log tables, not git history).
    Returns False (no-op) when nothing changed this minute."""
    subprocess.run(["git", "add", "-A"], cwd=state, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=state).returncode == 0:
        return False
    has_commit = subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=state,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if has_commit:
        subprocess.run(["git", "commit", "--amend", "-m", "data", "--no-edit"], cwd=state, check=True)
    else:
        subprocess.run(["git", "commit", "-m", "data"], cwd=state, check=True)
    subprocess.run(["git", "push", "--force", "origin", "HEAD:data"], cwd=state, check=True)
    return True


def run(minutes: int, state: Path, interval_seconds: float = 60.0, push: bool = True,
       real_sleep=time.sleep, cfg_overrides: dict | None = None) -> None:
    """cfg_overrides: shallow-merged into the loaded config (dict values merge one level deep,
    e.g. {"models": {"enabled": False}}). Mainly for tests, so they never need a real API key."""
    state = Path(state)
    cfg = _state_cfg(load_agent_config(), state)
    for key, value in (cfg_overrides or {}).items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        else:
            cfg[key] = value
    gen_cfg = g.load_config()
    log_path = state / "generator_log.csv"

    def after_each_import(seconds: float) -> None:
        real_sleep(seconds)
        _finish_one_minute(cfg, state, push)

    g.run(gen_cfg, minutes=minutes, interval_seconds=interval_seconds,
         inbox=cfg["inbox"], log_path=log_path, sleep=after_each_import)
    # g.run()'s sleep callback fires between imports, never after the last one, so the final
    # import still needs its own pass here.
    _finish_one_minute(cfg, state, push)


def _finish_one_minute(cfg: dict, state: Path, push: bool) -> None:
    summary = process_and_export(cfg, state)
    log.info("Processed one minute: %d held, %d incidents open",
             len(summary["held_imports"]), len(summary["incidents_open"]))
    if push:
        pushed = commit_and_push_data_branch(state)
        log.info("Pushed data branch: %s", pushed)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--minutes", type=int, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--interval-seconds", type=float, default=60.0)
    p.add_argument("--no-push", action="store_true", help="skip committing/pushing the data branch")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run(args.minutes, args.state, interval_seconds=args.interval_seconds, push=not args.no_push)


if __name__ == "__main__":
    main()
