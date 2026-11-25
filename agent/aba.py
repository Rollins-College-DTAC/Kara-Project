"""Reads the ABA's published Standard 509 / Employment Summary compilation spreadsheets and turns
them into import records for the pipeline.

Source: abarequireddisclosures.org (ABA Section of Legal Education), "Compilation - All Schools
Data". Real, public, school-submitted figures; the ABA "assumes no responsibility for
inaccuracies" in what schools submit, and the year in a file is the graduating class year.

Only the standard library is used (an .xlsx is a zip of XML), so there is no new dependency.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_xlsx(path: Path) -> tuple[str, list[dict]]:
    """First worksheet as (sheet name, rows as dicts keyed by the header row)."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")) for si in root.findall("m:si", NS)]
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheet_name = wb.find("m:sheets/m:sheet", NS).get("name")
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))

    grid: list[list] = []
    for row in sheet.iter(f"{{{NS['m']}}}row"):
        cells: dict[int, object] = {}
        for c in row.findall("m:c", NS):
            t = c.get("t")
            v = c.find("m:v", NS)
            if t == "inlineStr":
                value = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
            elif v is None or v.text is None:
                continue
            elif t == "s":
                value = shared[int(v.text)]
            elif t in ("str", "e"):
                value = v.text
            else:
                num = float(v.text)
                value = int(num) if num.is_integer() else num
            cells[_col_index(c.get("r"))] = value
        if cells:
            grid.append([cells.get(i) for i in range(max(cells) + 1)])
    if not grid:
        return sheet_name, []
    header = [str(h).strip() if h is not None else "" for h in grid[0]]
    rows = [dict(zip(header, r + [None] * (len(header) - len(r)))) for r in grid[1:] if r and r[0]]
    return sheet_name, rows


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def sheet_year(sheet_name: str) -> int:
    m = re.match(r"(\d{4})_", sheet_name)
    if not m:
        raise ValueError(f"cannot read a year from sheet name {sheet_name!r}")
    return int(m.group(1))


def _n(row: dict, key: str) -> int:
    v = row.get(key)
    return int(v) if isinstance(v, (int, float)) else 0


# Every employment-status bucket in the file. They sum to Total_GraduatesTotal for every school
# in every year checked, which is what the pipeline's categories-must-sum rule then re-verifies.
STATUS_BUCKETS = [
    "Employed_BarAdmissionRequiredTotal", "Employed_JDAdvantageTotal", "Employed_ProfessionPositionTotal",
    "Employed_OtherPositionTotal", "Employed_UndeterminableTotal", "Employed_LawSchoolTotal",
    "EnrolledInGraduateStudiesTotal", "EmployedStartDateDeferredTotal", "UnEmployedNotSeekingTotal",
    "UnEmployedSeekingTotal", "EmploymentStatusUnknownTotal",
]


def employment_record(row: dict, year: int) -> dict:
    """One school-year as a pipeline import record. The headline measure matches the project's:
    graduates in full-time, long-term, bar-passage-required jobs, over all graduates."""
    grads = _n(row, "Total_GraduatesTotal")
    bar = _n(row, "Employed_BarAdmissionRequiredFTLT")
    jd = _n(row, "Employed_JDAdvantageFTLT")
    unemployed = _n(row, "UnEmployedSeekingTotal") + _n(row, "UnEmployedNotSeekingTotal")
    all_buckets = sum(_n(row, k) for k in STATUS_BUCKETS)
    other = all_buckets - bar - jd - unemployed  # everything else: part-time/short-term, other job types, grad study, unknown
    name = str(row["SchoolName"]).strip()
    return {
        "source": "aba", "school_name": name, "school_key": slug(name), "grad_year": year,
        "grads": grads, "emp_unit": "count",
        "emp_bar_required": bar, "emp_jd_advantage": jd, "emp_other": other, "emp_unemployed": unemployed,
        "emp_biglaw": _n(row, "501Plus-Total"),
        "emp_fed_clerkship": _n(row, "Clerkships_Federal_Total"),
        "emp_public_interest": _n(row, "PublicInterest_Total"),
        "emp_government": _n(row, "Government_Total"),
        "emp_business": _n(row, "BusinessIndustry_Total"),
        "notes": "",
    }


def load_employment_file(path: Path) -> tuple[int, list[dict]]:
    sheet, rows = read_xlsx(path)
    year = sheet_year(sheet)
    return year, [employment_record(r, year) for r in rows]
