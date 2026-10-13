"""Tests for milestone 4 stage 1: clean, typed structured fields and consistency checks.

No model calls, no network: this step only touches the record's own admissions/employment
columns, independent of Claude's extraction from the notes field (milestone 3).
"""

import random

import pytest

from agent.clean import canonical_code, canonical_schools, clean_record, parse_date, parse_fraction, parse_int
from agent.db import connect
from agent.load import load_records
from agent.sql import RunContext, new_run_id
from generator import generate as g


@pytest.fixture
def cfg():
    c = g.load_config()
    c["seed"] = 11
    return c


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---------------------------------------------------------------- parsing helpers

def test_parse_int_handles_text_numbers():
    assert parse_int("123") == 123 and parse_int(123) == 123 and parse_int("") is None
    assert parse_int("N/A") is None and parse_int(None) is None


def test_parse_fraction_handles_percent_strings_and_fractions():
    assert parse_fraction("31.0%") == 0.31
    assert parse_fraction(0.31) == 0.31
    assert parse_fraction(31) == 0.31          # defensively treat > 1 as already a percent
    assert parse_fraction("n/a") is None


def test_parse_date_handles_all_four_generator_formats():
    assert parse_date("2024-03-05") == "2024-03-05"
    assert parse_date("03/05/2024") == "2024-03-05"
    assert parse_date("5 Mar 2024") == "2024-03-05"
    assert parse_date("March 5, 2024") == "2024-03-05"
    assert parse_date("garbage") is None


def test_canonical_code_undoes_code_variant_mangling():
    known = set(canonical_schools())
    assert canonical_code("LS-07") in known
    assert canonical_code("ls07") == canonical_code("LS-07")
    assert canonical_code(" LS-07") == canonical_code("LS-07")
    assert canonical_code("LS07") == canonical_code("LS-07")
    assert canonical_code("") is None and canonical_code(None) is None
    assert canonical_code("LS-99") is None  # only 30 schools exist


# ---------------------------------------------------------------- clean_record against real generator output

def _schools_and_profiles(cfg):
    schools = g.load_schools()
    profiles = {s["name"]: g.school_profile(s, cfg["seed"]) for s in schools}
    return schools, profiles


def test_clean_record_on_an_ordinary_record_has_no_flags(cfg):
    schools, profiles = _schools_and_profiles(cfg)
    r = random.Random(5)
    school = r.choice(schools)
    rec = g.build_record(school, profiles[school["name"]], 0.0, r, None, False)
    c = clean_record(rec)
    assert c["consistency_ok"] is True and c["consistency_flags"] == []
    assert c["school_code"] is not None and c["school_name"] == school["name"]
    assert c["emp_rate"] is not None and 0 <= c["emp_rate"] <= 1


@pytest.mark.parametrize("kind", ["counts_exceed_class", "percentiles_out_of_order", "categories_dont_sum"])
def test_seeded_consistency_anomaly_is_flagged(cfg, kind):
    schools, profiles = _schools_and_profiles(cfg)
    c = {**cfg, "warmup_imports": 0, "anomaly_rate": 1.0}
    r = random.Random(2)
    for i in range(60):
        records, meta = g.build_import(i, r, c, schools, profiles)
        if meta["anomaly"] != kind:
            continue
        flagged = [clean_record(rec) for rec in records]
        assert any(kind in cl["consistency_flags"] for cl in flagged), (kind, flagged)
        assert any(not cl["consistency_ok"] for cl in flagged)
        return
    pytest.fail(f"never generated {kind} in 60 tries")


def test_a_normal_batch_has_no_false_positives(cfg):
    """Clean (non-anomalous) imports must never trip a consistency rule."""
    schools, profiles = _schools_and_profiles(cfg)
    c = {**cfg, "anomaly_rate": 0.0, "hard_note_rate": 0.0}
    r = random.Random(9)
    for i in range(20):
        records, _ = g.build_import(i, r, c, schools, profiles)
        for rec in records:
            cl = clean_record(rec)
            assert cl["consistency_ok"], (rec, cl["consistency_flags"])


# ---------------------------------------------------------------- load_records (the Load step)

def test_load_records_holds_only_the_inconsistent_rows(cfg, tmp_path):
    schools, profiles = _schools_and_profiles(cfg)
    c = {**cfg, "warmup_imports": 0, "anomaly_rate": 1.0}
    r = random.Random(4)
    records = meta = None
    for i in range(60):
        records, meta = g.build_import(i, r, c, schools, profiles)
        if meta["anomaly"] == "counts_exceed_class":
            break
    assert meta["anomaly"] == "counts_exceed_class"

    conn = connect(tmp_path / "data" / "analytics.sqlite")
    ctx = RunContext(conn=conn, run_id=new_run_id(), file_name="f.csv")
    result = load_records(ctx, records)

    silver = rows(conn, "SELECT * FROM silver_records WHERE file_name = ? ORDER BY row_index", (ctx.file_name,))
    assert len(silver) == len(records)
    held = [s for s in silver if s["status"] == "held"]
    assert held and result["held"] == len(held)
    assert all("counts_exceed_class" in s["consistency_flags"] for s in held)
    assert all(s["status"] == "pending" for s in silver if s["consistency_ok"])

    incidents = rows(conn, "SELECT * FROM incident_log WHERE kind = 'consistency'")
    assert len(incidents) == len(held)

    run_log = rows(conn, "SELECT * FROM run_log WHERE step = 'load'")[0]
    assert run_log["status"] == "warning" and run_log["rows_rejected"] == len(held)


def test_load_records_is_idempotent(cfg, tmp_path):
    """Re-running Load on the same file (e.g. after a crash) must not duplicate silver rows."""
    schools, profiles = _schools_and_profiles(cfg)
    r = random.Random(1)
    records, _ = g.build_import(0, r, {**cfg, "anomaly_rate": 0.0}, schools, profiles)
    conn = connect(tmp_path / "data" / "analytics.sqlite")
    ctx = RunContext(conn=conn, run_id=new_run_id(), file_name="f.csv")
    load_records(ctx, records)
    load_records(ctx, records)
    assert len(rows(conn, "SELECT * FROM silver_records WHERE file_name = 'f.csv'")) == len(records)
