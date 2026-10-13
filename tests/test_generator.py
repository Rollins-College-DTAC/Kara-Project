"""Tests for the data generator (milestone 1). No network, no model calls."""

import csv
import hashlib
import json
import random

import pytest

from generator import generate as g


@pytest.fixture
def cfg():
    c = g.load_config()
    c["seed"] = 7
    return c


def run_fast(cfg, tmp_path, minutes, **overrides):
    """Run the generator without waiting between imports."""
    c = {**cfg, **overrides}
    files = g.run(c, minutes=minutes, interval_seconds=0, inbox=tmp_path / "inbox",
                  log_path=tmp_path / "generator_log.csv", sleep=lambda s: None)
    rows = list(csv.DictReader(open(tmp_path / "generator_log.csv", encoding="utf-8")))
    return files, rows


def test_every_file_name_is_unique_and_logged(cfg, tmp_path):
    # Many imports in the same wall-clock minute must still get different names.
    files, rows = run_fast(cfg, tmp_path, minutes=30)
    names = [f.name for f in files]
    assert len(names) == len(set(names))
    assert sorted(r["file_name"] for r in rows) == sorted(names)
    assert all(f.exists() for f in files)


def test_formats_alternate_and_record_counts_are_in_range(cfg, tmp_path):
    _, rows = run_fast(cfg, tmp_path, minutes=12, renamed_copy_rate=0, duplicate_row_rate=0)
    imports = [r for r in rows if r["event"] == "import"]
    assert [r["format"] for r in imports] == ["csv", "json"] * 6
    assert all(cfg["records_min"] <= int(r["n_records"]) <= cfg["records_max"] for r in imports)


def test_files_are_readable_and_have_all_fields(cfg, tmp_path):
    files, _ = run_fast(cfg, tmp_path, minutes=4, renamed_copy_rate=0)
    for f in files:
        if f.suffix == ".csv":
            data = list(csv.DictReader(open(f, encoding="utf-8")))
        else:
            data = json.load(open(f, encoding="utf-8"))
        assert data and all(set(g.FIELDS) <= set(row) for row in data)


def test_no_anomalies_during_warmup(cfg, tmp_path):
    _, rows = run_fast(cfg, tmp_path, minutes=cfg["warmup_imports"], anomaly_rate=1.0, renamed_copy_rate=0)
    assert all(r["anomaly"] == "none" for r in rows)


def test_seeded_anomalies_are_logged_with_expected_detector(cfg, tmp_path):
    _, rows = run_fast(cfg, tmp_path, minutes=40, anomaly_rate=1.0, renamed_copy_rate=0)
    anomalous = [r for r in rows if r["anomaly"] != "none"]
    assert len(anomalous) == 40 - cfg["warmup_imports"]
    for r in anomalous:
        assert r["anomaly"] in g.ANOMALIES
        assert r["expected_detector"] == g.ANOMALIES[r["anomaly"]]


def test_anomaly_rate_is_about_one_in_ten(cfg, tmp_path):
    _, rows = run_fast(cfg, tmp_path, minutes=400, renamed_copy_rate=0)
    imports = [r for r in rows if r["event"] == "import"]
    share = sum(r["anomaly"] != "none" for r in imports) / len(imports)
    assert 0.05 < share < 0.15


def numeric(v):
    return float(str(v).replace(",", "")) if str(v).strip() not in ("", "N/A", "n/a") else None


def test_clean_imports_are_internally_consistent(cfg, tmp_path):
    """Records in non-anomalous imports must pass the checks that anomalies are built to break."""
    files, rows = run_fast(cfg, tmp_path, minutes=20, anomaly_rate=0, duplicate_row_rate=0, renamed_copy_rate=0)
    for f in files:
        data = json.load(open(f)) if f.suffix == ".json" else list(csv.DictReader(open(f, encoding="utf-8")))
        for rec in data:
            grads, size = numeric(rec["grads"]), numeric(rec["class_size"])
            parts = [numeric(rec[k]) for k in ("emp_bar_required", "emp_jd_advantage", "emp_other", "emp_unemployed")]
            assert grads <= size
            if rec["emp_unit"] == "count":
                assert sum(parts) == grads
                assert max(parts) <= size
            else:
                assert abs(sum(parts) - 100) < 0.6  # rounding to one decimal
            assert numeric(rec["lsat_25"]) <= numeric(rec["lsat_50"]) <= numeric(rec["lsat_75"])


def test_seeded_consistency_anomalies_actually_break_the_rules(cfg, tmp_path):
    for kind in ("counts_exceed_class", "percentiles_out_of_order", "categories_dont_sum"):
        sub = tmp_path / kind
        sub.mkdir()
        c = {**cfg, "warmup_imports": 0, "anomaly_rate": 1.0}
        schools = g.load_schools()
        profiles = {s["name"]: g.school_profile(s, c["seed"]) for s in schools}
        found = False
        r = random.Random(1)
        for i in range(60):
            # Force this anomaly kind by retrying until the generator picks it.
            records, meta = g.build_import(i, r, c, schools, profiles)
            if meta["anomaly"] != kind:
                continue
            found = True
            broken = 0
            for rec in records:
                grads, size = numeric(rec["grads"]), numeric(rec["class_size"])
                parts = [numeric(rec[k]) for k in ("emp_bar_required", "emp_jd_advantage", "emp_other", "emp_unemployed")]
                if kind == "counts_exceed_class":
                    broken += parts[0] > size
                elif kind == "percentiles_out_of_order":
                    broken += numeric(rec["lsat_25"]) > numeric(rec["lsat_75"])
                else:
                    broken += sum(parts) != grads
            assert broken >= 1, kind
            break
        assert found, f"never generated {kind}"


def test_rate_spike_moves_the_batch_mean(cfg):
    """A spike must be large enough that a z-score on the batch mean can see it."""
    c = {**cfg, "warmup_imports": 0, "anomaly_rate": 0.0, "duplicate_row_rate": 0, "injection_rate": 0,
         "records_min": 10, "records_max": 10}
    schools = g.load_schools()
    profiles = {s["name"]: g.school_profile(s, c["seed"]) for s in schools}

    def mean_rate(shift_bonus):
        r = random.Random(3)
        rates = []
        for s in r.sample(schools, 10):
            rec = g.build_record(s, profiles[s["name"]], shift_bonus, random.Random(5), None, False)
            grads = numeric(rec["grads"])
            v = numeric(rec["emp_bar_required"])
            rates.append(v / grads if rec["emp_unit"] == "count" else v / 100)
        return sum(rates) / len(rates)

    assert mean_rate(0.25) - mean_rate(0.0) > 0.15


def test_same_seed_gives_same_data(cfg, tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    fa, _ = run_fast(cfg, a, minutes=6)
    fb, _ = run_fast(cfg, b, minutes=6)
    digest = lambda files: [hashlib.sha256(f.read_bytes()).hexdigest() for f in files]
    assert digest(fa) == digest(fb)


def test_renamed_copy_has_same_bytes_but_new_name(cfg, tmp_path):
    files, rows = run_fast(cfg, tmp_path, minutes=10, renamed_copy_rate=1.0)
    copies = [r for r in rows if r["event"] == "renamed_copy"]
    assert copies
    for row in copies:
        copy = tmp_path / "inbox" / row["file_name"]
        original = tmp_path / "inbox" / row["renamed_copy_of"]
        assert copy.name != original.name
        assert copy.read_bytes() == original.read_bytes()


def test_injection_records_are_flagged_in_the_log(cfg, tmp_path):
    files, rows = run_fast(cfg, tmp_path, minutes=6, injection_rate=1.0, renamed_copy_rate=0, duplicate_row_rate=0)
    assert all(int(r["injection_records"]) == int(r["n_records"]) for r in rows)
    for f in files:
        data = json.load(open(f)) if f.suffix == ".json" else list(csv.DictReader(open(f, encoding="utf-8")))
        assert all(rec["notes"] in g.INJECTION_NOTES for rec in data)


def test_all_schools_are_invented_and_unique():
    schools = g.load_schools()
    names = [s["name"] for s in schools]
    assert len(names) == 30 and len(set(names)) == 30
    assert len({s["code"] for s in schools}) == 30


def test_no_secrets_in_example_env():
    from pathlib import Path
    text = (g.ROOT / ".env.example").read_text()
    for line in text.splitlines():
        if line.startswith(("ANTHROPIC_API_KEY=", "JEV_API_KEY=")):
            assert line.split("=", 1)[1].strip() == ""
    assert ".env" in (g.ROOT / ".gitignore").read_text()
