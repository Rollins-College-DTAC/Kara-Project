"""Tests for agent/aba.py and scripts/import_aba.py: reading the ABA's real Employment Summary
spreadsheets and turning them into pipeline imports. Unit tests use a tiny synthetic .xlsx built
with the standard library; the last tests check the real downloaded files when they're present."""

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from agent.aba import STATUS_BUCKETS, employment_record, load_employment_file, read_xlsx, sheet_year, slug
from agent.clean import clean_record
from agent.config import ROOT

REAL = ROOT / "data_real"


def make_xlsx(path: Path, sheet: str, header: list[str], rows: list[list]) -> Path:
    strings: list[str] = []

    def cell(ref, v):
        if isinstance(v, str):
            strings.append(v)
            return f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>'
        return f'<c r="{ref}"><v>{v}</v></c>'

    cols = lambda i: chr(65 + i)
    body = "".join(
        f'<row r="{ri + 1}">' + "".join(cell(f"{cols(ci)}{ri + 1}", v) for ci, v in enumerate(r) if v is not None) + "</row>"
        for ri, r in enumerate([header] + rows))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                      f'<sheets><sheet name="{sheet}" sheetId="1"/></sheets></workbook>')
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                                f"<sheetData>{body}</sheetData></worksheet>")
        z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
    return path


def test_slug_and_sheet_year():
    assert slug("Akron, The University of") == "akron-the-university-of"
    assert sheet_year("2025_EQSummaryData") == 2025
    with pytest.raises(ValueError):
        sheet_year("Sheet1")


def test_read_xlsx_returns_header_keyed_rows(tmp_path):
    f = make_xlsx(tmp_path / "t.xlsx", "2024_EQSummaryData", ["SchoolName", "Total_GraduatesTotal"],
                  [["Test Law", 100], ["Other Law", 50]])
    sheet, rows = read_xlsx(f)
    assert sheet == "2024_EQSummaryData"
    assert rows == [{"SchoolName": "Test Law", "Total_GraduatesTotal": 100},
                    {"SchoolName": "Other Law", "Total_GraduatesTotal": 50}]


def row(**over):
    base = {k: 0 for k in STATUS_BUCKETS}
    base.update({"SchoolName": "Test Law School", "Total_GraduatesTotal": 100,
                 "Employed_BarAdmissionRequiredTotal": 70, "Employed_BarAdmissionRequiredFTLT": 60,
                 "Employed_JDAdvantageTotal": 10, "Employed_JDAdvantageFTLT": 8,
                 "Employed_OtherPositionTotal": 5, "UnEmployedSeekingTotal": 8, "UnEmployedNotSeekingTotal": 2,
                 "EmploymentStatusUnknownTotal": 5, "501Plus-Total": 12, "Clerkships_Federal_Total": 3})
    base.update(over)
    return base


def test_employment_record_uses_ftlt_bar_required_as_the_headline_numerator():
    rec = employment_record(row(), 2025)
    assert rec["emp_bar_required"] == 60 and rec["emp_jd_advantage"] == 8 and rec["emp_unemployed"] == 10
    assert rec["emp_biglaw"] == 12 and rec["emp_fed_clerkship"] == 3 and rec["school_key"] == "test-law-school"


def test_categories_sum_to_graduates_so_the_pipeline_check_passes():
    rec = employment_record(row(), 2025)
    assert rec["emp_bar_required"] + rec["emp_jd_advantage"] + rec["emp_other"] + rec["emp_unemployed"] == 100


def test_a_real_school_record_cleans_without_any_consistency_flag():
    c = clean_record(employment_record(row(), 2025))
    assert c["consistency_ok"] and c["school_code"] == "test-law-school" and c["school_name"] == "Test Law School"
    assert c["data_source"] == "aba" and c["emp_rate"] == 0.6 and c["emp_biglaw"] == 12


def test_a_simulated_record_is_still_marked_simulated():
    assert clean_record({"school_code": "LS-01", "grads": "10"})["data_source"] == "simulated"


def test_blank_or_text_cells_count_as_zero_not_a_crash():
    rec = employment_record(row(**{"Employed_JDAdvantageFTLT": "n/a", "501Plus-Total": None}), 2025)
    assert rec["emp_jd_advantage"] == 0 and rec["emp_biglaw"] == 0


real_files = pytest.mark.skipif(not (REAL / "Employment_Summary_2025.xlsx").exists(), reason="real data not downloaded")


@real_files
def test_real_2025_file_loads_every_school_and_its_buckets_sum_to_graduates():
    year, records = load_employment_file(REAL / "Employment_Summary_2025.xlsx")
    assert year == 2025 and len(records) > 150
    for r in records:
        assert r["emp_bar_required"] + r["emp_jd_advantage"] + r["emp_other"] + r["emp_unemployed"] == r["grads"], r["school_name"]


@real_files
def test_import_script_writes_one_json_per_class_oldest_first(tmp_path):
    spec = importlib.util.spec_from_file_location("import_aba", ROOT / "scripts" / "import_aba.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    written = mod.convert(REAL, tmp_path)
    assert [p.name for p in written] == sorted(p.name for p in written)
    assert json.loads(written[-1].read_text())[0]["source"] == "aba"


# ---------------------------------------------------------------- school profiles

from agent.aba import build_school_profiles, estimated_net_tuition, profile_flags, to_frac, to_num  # noqa: E402
from agent.aba_load import load_profiles  # noqa: E402
from agent.db import connect  # noqa: E402
from agent.sql import RunContext, new_run_id  # noqa: E402


def test_to_num_and_to_frac_handle_the_formats_the_aba_uses():
    assert to_num("$22,359") == 22359.0 and to_num(" 157 ") == 157.0 and to_num(94) == 94.0
    assert to_num("N/A") is None and to_num("") is None and to_num(None) is None
    assert to_frac("70.16%") == 0.7016 and to_frac(58.53) == 0.5853 and to_frac("") is None


def test_estimated_net_tuition_subtracts_the_expected_grant():
    p = {"tuition_resident": 50000, "fees": 2000, "grants_share": 0.5, "grant_median_ft": 20000}
    assert estimated_net_tuition(p) == 42000.0  # 52,000 sticker less 0.5 x 20,000
    assert estimated_net_tuition({"tuition_resident": None}) is None
    assert estimated_net_tuition({"tuition_resident": 1000, "grants_share": 1.0, "grant_median_ft": 9000}) == 0.0


def test_profile_flags_catch_bad_source_data():
    assert profile_flags({"lsat_25": 150, "lsat_50": 155, "lsat_75": 160}) == []
    assert "lsat_percentiles_out_of_order" in profile_flags({"lsat_25": 160, "lsat_50": 155, "lsat_75": 150})
    assert "grants_share_out_of_range" in profile_flags({"grants_share": 1.02})
    assert "tuition_not_positive" in profile_flags({"tuition_resident": 0})


def test_load_profiles_writes_rows_and_logs_the_sql(tmp_path):
    conn = connect(tmp_path / "d.sqlite")
    ctx = RunContext(conn=conn, run_id=new_run_id(), file_name="aba_school_profiles")
    good = {"school_key": "a", "school_name": "A Law", "flags": [], "lsat_50": 160.0}
    bad = {"school_key": "b", "school_name": "B Law", "flags": ["grants_share_out_of_range"]}
    assert load_profiles(ctx, [good, bad]) == {"loaded": 2, "flagged": 1}
    assert conn.execute("select count(*), sum(consistency_ok) from school_profile").fetchone()[:] == (2, 1)
    assert conn.execute("select count(*) from sql_log where step = 'profile'").fetchone()[0] == 2


profile_files = pytest.mark.skipif(not (REAL / "First_Year_Class_2025.xlsx").exists(), reason="509 files not downloaded")


@profile_files
def test_real_profiles_cover_every_school_with_public_private_and_plausible_values():
    profiles = build_school_profiles(REAL)
    assert len(profiles) >= 190
    assert {p["school_type"] for p in profiles if p["school_type"]} == {"Public", "Private"}
    yale = next(p for p in profiles if p["school_key"] == "yale-university")
    assert yale["lsat_50"] > 170 and yale["acceptance_rate"] < 0.1 and yale["bar_first_time_pass"] > 0.9
    assert all(p["lsat_25"] <= p["lsat_50"] <= p["lsat_75"] for p in profiles if None not in (p["lsat_25"], p["lsat_50"], p["lsat_75"]))


@profile_files
def test_per_credit_schools_get_a_labeled_estimate_instead_of_zero_tuition():
    profiles = build_school_profiles(REAL)
    per_credit = [p for p in profiles if p["tuition_basis"] == "per_credit_estimate"]
    assert per_credit and all(p["tuition_resident"] > 0 for p in per_credit)
    assert not any("tuition_not_positive" in p["flags"] for p in profiles)
