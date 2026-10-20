"""Tests for agent/cloud_loop.py: the cloud pipeline's per-minute processing and its
commit-to-the-data-branch step.

The git test uses a throwaway local bare repo as a fake 'origin' -- never a real remote, and
never this project's own repo -- so it's safe to run anywhere, including CI.
"""

import subprocess

import pytest

from agent.cloud_loop import commit_and_push_data_branch, process_and_export, run
from agent.config import load_agent_config
from agent.db import connect
from generator import generate as g


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def fake_origin_and_worktree(tmp_path):
    """A bare repo standing in for GitHub, plus a clone of it on an orphan `data` branch --
    exactly what .github/workflows/pipeline.yml sets up before calling cloud_loop."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git("init", "--bare", cwd=origin)

    state = tmp_path / "state"
    state.mkdir()
    git("init", cwd=state)
    git("config", "user.email", "test@example.com", cwd=state)
    git("config", "user.name", "Test", cwd=state)
    git("checkout", "--orphan", "data", cwd=state)
    git("remote", "add", "origin", str(origin), cwd=state)
    return origin, state


def test_commit_and_push_creates_the_first_commit_on_data(fake_origin_and_worktree):
    origin, state = fake_origin_and_worktree
    (state / "analytics.sqlite").write_text("fake db v1")
    assert commit_and_push_data_branch(state) is True
    log = subprocess.run(["git", "log", "--oneline", "data"], cwd=origin, capture_output=True, text=True)
    assert len(log.stdout.strip().splitlines()) == 1


def test_commit_and_push_amends_instead_of_growing_history(fake_origin_and_worktree):
    origin, state = fake_origin_and_worktree
    (state / "analytics.sqlite").write_text("v1")
    commit_and_push_data_branch(state)
    (state / "analytics.sqlite").write_text("v2")
    commit_and_push_data_branch(state)
    (state / "analytics.sqlite").write_text("v3")
    commit_and_push_data_branch(state)

    log = subprocess.run(["git", "log", "--oneline", "data"], cwd=origin, capture_output=True, text=True)
    assert len(log.stdout.strip().splitlines()) == 1  # still one commit, not three
    content = subprocess.run(["git", "show", "data:analytics.sqlite"], cwd=origin,
                             capture_output=True, text=True).stdout
    assert content == "v3"  # but it carries the latest content


def test_commit_and_push_is_a_no_op_when_nothing_changed(fake_origin_and_worktree):
    origin, state = fake_origin_and_worktree
    (state / "analytics.sqlite").write_text("v1")
    assert commit_and_push_data_branch(state) is True
    assert commit_and_push_data_branch(state) is False  # nothing new to commit


def test_process_and_export_runs_one_minute_of_the_pipeline(tmp_path):
    state = tmp_path / "state"
    cfg = load_agent_config()
    cfg["inbox"], cfg["processed"], cfg["quarantine"] = state / "inbox", state / "processed", state / "quarantine"
    cfg["data_dir"] = state / "data"
    cfg["sqlite_path"], cfg["raw_path"] = cfg["data_dir"] / "analytics.sqlite", cfg["data_dir"] / "raw.json"
    cfg["models"]["enabled"] = False
    cfg["settle_seconds"] = 0  # the test writes and scans in the same instant

    gen_cfg = g.load_config()
    schools = g.load_schools()
    profiles = {s["name"]: g.school_profile(s, gen_cfg["seed"]) for s in schools}
    import random
    records, _ = g.build_import(0, random.Random(1), {**gen_cfg, "anomaly_rate": 0.0}, schools, profiles)
    cfg["inbox"].mkdir(parents=True)
    g.write_records(cfg["inbox"] / "import.csv", records, "csv")

    summary = process_and_export(cfg, state)
    assert (state / "exports" / "daily_summary.json").exists()
    assert summary["imports_processed_today"] == 1

    conn = connect(cfg["sqlite_path"])
    assert conn.execute("SELECT COUNT(*) FROM silver_records").fetchone()[0] == len(records)


def test_run_processes_every_minute_and_pushes_each_time(fake_origin_and_worktree):
    # A real, short sleep (not interval_seconds=0 with a no-op sleep): the agent's own
    # settle_seconds skips a file written less than a second ago, so the test needs to behave
    # like real time actually passed between imports, just compressed to ~1s instead of 60s.
    import time as _time
    origin, state = fake_origin_and_worktree
    run(minutes=3, state=state, interval_seconds=1.1, push=True, real_sleep=_time.sleep,
       cfg_overrides={"models": {"enabled": False}})  # never a real API call from a test

    log = subprocess.run(["git", "log", "--oneline", "data"], cwd=origin, capture_output=True, text=True)
    assert len(log.stdout.strip().splitlines()) == 1  # amended each time, still one commit
    files = subprocess.run(["git", "show", "--name-only", "--format=", "data"], cwd=origin,
                           capture_output=True, text=True).stdout.splitlines()
    assert "exports/daily_summary.json" in files
    assert any(f.startswith("data/analytics.sqlite") or f == "data/analytics.sqlite" for f in files)
