"""Tests for scripts/apply_review.py: the review.yml workflow's Release/Reject logic."""

import importlib.util
import subprocess

import pytest

from agent.config import ROOT
from agent.db import connect
from agent.sql import now_iso


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def ar():
    spec = importlib.util.spec_from_file_location("apply_review", ROOT / "scripts" / "apply_review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def state_with_held_import(tmp_path):
    state = tmp_path / "state"
    (state / "data").mkdir(parents=True)
    git("init", cwd=state)
    git("config", "user.email", "test@example.com", cwd=state)
    git("config", "user.name", "Test", cwd=state)

    conn = connect(state / "data" / "analytics.sqlite")
    conn.execute("INSERT INTO silver_records (file_name, row_index, run_id, school_code, grads, "
                "emp_bar_required, emp_rate, consistency_ok, consistency_flags, status, landed_at) "
                "VALUES ('f.csv', 0, 'run-1', 'LS-01', 100, 90, 0.9, 1, '[]', 'held', ?)", (now_iso(),))
    conn.execute("INSERT INTO run_log (run_id, step, file_name, started_at) VALUES "
                "('run-1', 'decide', 'f.csv', ?)", (now_iso(),))
    conn.execute("INSERT INTO incident_log (incident_id, run_id, kind, detail, status, opened_at) "
                "VALUES ('inc-1', 'run-1', 'trigger', 'f.csv: fired', 'open', ?)", (now_iso(),))
    conn.commit()
    conn.close()
    return state


def test_file_name_for_incident_looks_up_through_run_log(ar, state_with_held_import):
    conn = connect(state_with_held_import / "data" / "analytics.sqlite")
    assert ar.file_name_for_incident(conn, "inc-1") == "f.csv"


def test_file_name_for_incident_raises_for_an_unknown_incident(ar, state_with_held_import):
    conn = connect(state_with_held_import / "data" / "analytics.sqlite")
    with pytest.raises(SystemExit, match="no open trigger incident"):
        ar.file_name_for_incident(conn, "inc-does-not-exist")


def test_main_applies_release_and_commits_without_pushing(ar, state_with_held_import, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["apply_review.py", "--state", str(state_with_held_import),
                                     "--incident-id", "inc-1", "--decision", "release",
                                     "--reviewer", "KB", "--no-push"])
    ar.main()
    out = capsys.readouterr().out
    assert "released f.csv: 1 rows" in out

    conn = connect(state_with_held_import / "data" / "analytics.sqlite")
    status = conn.execute("SELECT status FROM silver_records WHERE file_name = 'f.csv'").fetchone()["status"]
    assert status == "published"
    incident = conn.execute("SELECT status, decided_by FROM incident_log WHERE incident_id = 'inc-1'").fetchone()
    assert incident["status"] == "released" and incident["decided_by"] == "KB"
