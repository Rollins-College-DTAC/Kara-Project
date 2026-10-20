"""Regression test: scripts/compute_stats.py must only read published silver_records
(references/requirements.md: "Analytics (gold)... published imports only"). A held, pending
or rejected row must never leak into the statistics, even though it's still consistency_ok=1.
"""

import importlib.util

import pytest

from agent.db import connect
from agent.sql import now_iso


@pytest.fixture
def cs():
    from agent.config import ROOT
    spec = importlib.util.spec_from_file_location("compute_stats", ROOT / "scripts" / "compute_stats.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def seed(conn, status, school_code="LS-01", emp_rate=0.9, grads=100, row_index=0):
    conn.execute(
        "INSERT INTO silver_records (file_name, row_index, run_id, school_code, grads, emp_bar_required, "
        "emp_rate, consistency_ok, consistency_flags, status, landed_at) "
        "VALUES ('f.csv', ?, 'r', ?, ?, ?, ?, 1, '[]', ?, ?)",
        (row_index, school_code, grads, round(grads * emp_rate), emp_rate, status, now_iso()))
    conn.commit()


def test_held_pending_and_rejected_rows_are_excluded_from_the_stats(tmp_path, cs, monkeypatch):
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    seed(conn, "published", emp_rate=0.9, row_index=0)
    seed(conn, "held", emp_rate=0.1, row_index=1)       # a wild outlier that must not leak in
    seed(conn, "pending", emp_rate=0.1, row_index=2)
    seed(conn, "rejected", emp_rate=0.1, row_index=3)
    conn.close()

    cfg = {"sqlite_path": tmp_path / "data" / "analytics.sqlite"}
    results = cs.run(cfg)
    wilson = next(r for r in results if r["method"] == "wilson_ci")
    assert wilson["result"] == 0.9  # only the one published row counted, not the three outliers
