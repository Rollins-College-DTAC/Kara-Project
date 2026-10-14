"""Tests for milestone 2: Detect, Land, run_log and sql_log. No network, no model calls."""

import json
import os
import shutil
import time

import pytest
from tinydb import TinyDB

from agent import loop
from agent.db import connect
from agent.land import parse_file
from agent.sql import RunContext, new_run_id, run_sql
from generator import generate as g


@pytest.fixture
def cfg(tmp_path):
    data = tmp_path / "data"
    return {
        "inbox": tmp_path / "inbox", "processed": tmp_path / "processed",
        "quarantine": tmp_path / "quarantine", "data_dir": data,
        "sqlite_path": data / "analytics.sqlite", "raw_path": data / "raw.json",
        "scan_seconds": 15, "settle_seconds": 0,
    }


def generate(cfg, tmp_path, minutes, **overrides):
    gcfg = {**g.load_config(), "seed": 7, "renamed_copy_rate": 0, "duplicate_row_rate": 0, **overrides}
    return g.run(gcfg, minutes=minutes, interval_seconds=0, inbox=cfg["inbox"],
                 log_path=tmp_path / "generator_log.csv", sleep=lambda s: None)


def sql(cfg, query, params=()):
    conn = connect(cfg["sqlite_path"])
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def raw_docs(cfg):
    if not cfg["raw_path"].exists():
        return []
    with TinyDB(cfg["raw_path"]) as db:
        return db.table("raw_records").all()


def put(cfg, name, content):
    cfg["inbox"].mkdir(parents=True, exist_ok=True)
    path = cfg["inbox"] / name
    path.write_bytes(content if isinstance(content, bytes) else content.encode())
    return path


# ---------------------------------------------------------------- detect and skip-if-seen

def test_new_file_is_landed_and_moved(cfg, tmp_path):
    generate(cfg, tmp_path, 1)
    results = loop.scan_once(cfg)
    assert [outcome for _, outcome in results] == ["landed"]
    assert list(cfg["inbox"].iterdir()) == []
    assert len(list(cfg["processed"].glob("law_school_outcomes_*"))) == 1
    reg = sql(cfg, "SELECT status, rows_landed FROM file_registry")[0]
    assert reg["status"] == "landed" and reg["rows_landed"] == len(raw_docs(cfg))


def test_renamed_copy_is_skipped_and_shown_in_the_log(cfg, tmp_path):
    original = generate(cfg, tmp_path, 1)[0]
    loop.scan_once(cfg)
    before = len(raw_docs(cfg))

    # The same bytes re-sent under a new name.
    copy = put(cfg, "law_school_outcomes_resend.csv", (cfg["processed"] / original.name).read_bytes())
    results = loop.scan_once(cfg)

    assert results == [(copy.name, "duplicate")]
    assert len(raw_docs(cfg)) == before                       # nothing landed twice
    assert (cfg["processed"] / "duplicates" / copy.name).exists()
    row = sql(cfg, "SELECT status, message FROM run_log WHERE file_name = ? AND step = 'detect'", (copy.name,))[0]
    assert row["status"] == "warning"
    assert original.name in row["message"] and "skipped" in row["message"]
    assert not sql(cfg, "SELECT 1 FROM run_log WHERE file_name = ? AND step = 'land'", (copy.name,))


def test_same_file_re_sent_later_is_skipped_again(cfg, tmp_path):
    original = generate(cfg, tmp_path, 1)[0]
    loop.scan_once(cfg)
    for n in range(2):
        put(cfg, f"again_{n}.csv", (cfg["processed"] / original.name).read_bytes())
        assert loop.scan_once(cfg)[0][1] == "duplicate"
    assert len(sql(cfg, "SELECT 1 FROM file_registry")) == 1


def test_generator_resends_are_all_caught(cfg, tmp_path):
    generate(cfg, tmp_path, 12, renamed_copy_rate=1.0)
    outcomes = [o for _, o in loop.scan_once(cfg)]
    resends = len([f for f in os.listdir(cfg["processed"] / "duplicates")])
    assert outcomes.count("duplicate") == resends and resends >= 1
    assert outcomes.count("landed") == 12                     # one landed file per distinct import
    assert len(sql(cfg, "SELECT 1 FROM file_registry")) == 12


# ---------------------------------------------------------------- land

def test_records_land_unchanged_and_tagged(cfg, tmp_path):
    generate(cfg, tmp_path, 4, injection_rate=1.0, duplicate_row_rate=1.0)
    loop.scan_once(cfg)
    docs = raw_docs(cfg)
    by_file = {}
    for d in docs:
        by_file.setdefault(d["file_name"], []).append(d)
    assert len(by_file) == 4
    for name, items in by_file.items():
        original = parse_file(cfg["processed"] / name)
        assert [i["record"] for i in sorted(items, key=lambda i: i["row_index"])] == original
        for i in items:
            assert i["run_id"].startswith("run-") and len(i["file_sha256"]) == 64
    # Text that tries to give instructions is stored as plain data, untouched.
    assert all(d["record"]["notes"] in g.INJECTION_NOTES for d in docs)


def test_duplicate_rows_inside_a_file_are_kept_raw(cfg, tmp_path):
    generate(cfg, tmp_path, 1, duplicate_row_rate=1.0)
    loop.scan_once(cfg)
    records = [d["record"] for d in raw_docs(cfg)]
    assert len(records) > len({json.dumps(r, sort_keys=True) for r in records})  # cleaning is a later milestone


# ---------------------------------------------------------------- run_log and sql_log

def test_every_step_has_a_start_and_a_finish(cfg, tmp_path):
    generate(cfg, tmp_path, 3)
    loop.scan_once(cfg)
    rows = sql(cfg, "SELECT * FROM run_log")
    assert {r["step"] for r in rows} == {"detect", "land", "load", "decide", "act"}  # milestone 4
    for r in rows:
        assert r["started_at"] and r["finished_at"] and r["finished_at"] >= r["started_at"]
        assert r["status"] == "ok" and len(r["file_sha256"]) == 64
    for r in rows:
        if r["step"] == "land":
            assert r["rows_in"] == r["rows_out"] and r["rows_out"] > 0
            assert "moved to processed/" in r["message"]


def test_sql_is_logged_with_placeholders_and_file_names(cfg, tmp_path):
    generate(cfg, tmp_path, 2)
    loop.scan_once(cfg)
    rows = sql(cfg, "SELECT * FROM sql_log")
    assert rows
    for r in rows:
        assert r["run_id"] and r["file_name"] and r["step"] in ("detect", "land", "load", "decide", "act")
        assert "?" in r["sql_text"]
        assert r["file_name"] not in r["sql_text"]            # values never pasted into SQL text
        assert r["duration_ms"] is not None
    inserts = [r for r in rows if r["sql_text"].startswith("INSERT INTO file_registry")]
    assert inserts and all(r["file_name"] in r["params_json"] for r in inserts)


def test_log_table_writes_are_not_logged(cfg, tmp_path):
    generate(cfg, tmp_path, 2)
    loop.scan_once(cfg)
    for r in sql(cfg, "SELECT sql_text FROM sql_log"):
        assert not any(t in r["sql_text"] for t in ("run_log", "sql_log", "incident_log"))


def test_long_text_values_are_shortened_in_sql_log(cfg):
    conn = connect(cfg["sqlite_path"])
    ctx = RunContext(conn=conn, run_id=new_run_id(), file_name="x.csv")
    run_sql(ctx, "detect", "SELECT ?", ("A" * 500,))
    logged = conn.execute("SELECT params_json FROM sql_log").fetchone()["params_json"]
    conn.close()
    assert len(logged) < 150 and "+420 chars" in logged


def test_values_with_quotes_cannot_change_the_sql(cfg):
    conn = connect(cfg["sqlite_path"])
    ctx = RunContext(conn=conn, run_id=new_run_id(), file_name="x.csv")
    evil = "x'); DROP TABLE file_registry; --"
    run_sql(ctx, "detect", "INSERT INTO file_registry (sha256, file_name) VALUES (?, ?)", ("h1", evil))
    row = conn.execute("SELECT file_name FROM file_registry WHERE sha256 = 'h1'").fetchone()
    conn.close()
    assert row["file_name"] == evil


# ---------------------------------------------------------------- quarantine

BAD_FILES = [
    ("broken.json", "{not valid json"),
    ("object_not_list.json", '{"school_name": "x"}'),
    ("ragged.csv", "a,b\n1,2\n3,4,5\n"),
    ("empty.csv", "a,b\n"),
    ("notes.txt", "hello"),
]


@pytest.mark.parametrize("name,content", BAD_FILES)
def test_unreadable_files_go_to_quarantine_with_an_incident(cfg, name, content):
    put(cfg, name, content)
    assert loop.scan_once(cfg) == [(name, "quarantined")]
    assert (cfg["quarantine"] / name).exists() and not (cfg["inbox"] / name).exists()
    assert raw_docs(cfg) == []                                # nothing partial reached the raw layer
    land = sql(cfg, "SELECT status, message FROM run_log WHERE step = 'land'")[0]
    assert land["status"] == "failed" and "ParseError" in land["message"]
    inc = sql(cfg, "SELECT kind, status, detail FROM incident_log")[0]
    assert inc["kind"] == "failure" and inc["status"] == "open" and name in inc["detail"]
    assert sql(cfg, "SELECT status FROM file_registry")[0]["status"] == "quarantined"


def test_a_bad_file_does_not_block_the_good_ones(cfg, tmp_path):
    put(cfg, "a_broken.json", "{oops")
    generate(cfg, tmp_path, 2)
    outcomes = dict(loop.scan_once(cfg))
    assert outcomes["a_broken.json"] == "quarantined"
    assert list(outcomes.values()).count("landed") == 2


# ---------------------------------------------------------------- scanning

def test_files_still_being_written_are_left_alone(cfg):
    cfg["settle_seconds"] = 60
    path = put(cfg, "fresh.json", "[]")
    assert loop.scan_once(cfg) == []
    assert path.exists()
    old = time.time() - 120
    os.utime(path, (old, old))
    assert loop.scan_once(cfg) == [("fresh.json", "quarantined")]  # settled now, and empty


def test_empty_or_missing_inbox_is_fine(cfg):
    assert loop.scan_once(cfg) == []
    cfg["inbox"].mkdir()
    assert loop.scan_once(cfg) == []
