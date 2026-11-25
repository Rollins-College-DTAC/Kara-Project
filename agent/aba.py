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


# The ABA renamed about thirty schools between the 2023 and 2024 reports (and spells names in capitals
# before 2024). Each old name below is the same institution as the current one on the right; it was
# checked by hand against the 2024 list, and tests/test_aba.py checks class sizes stay continuous.
# Schools that closed or merged (Arizona Summit, Whittier, the Savannah campus, and Penn State Law
# and Dickinson, which became one school in 2024 with three times Dickinson's class) are deliberately
# not mapped: a trend across a merger would be misleading.
NAME_ALIASES = {
    "ARKANSAS, FAYETTEVILLE, UNIVERSITY OF": "Arkansas, University of",
    "ARKANSAS, LITTLE ROCK, UNIVERSITY OF": "Arkansas at Little Rock, University of",
    "CAPITAL UNIVERSITY": "Capital University Law School",
    "CARDOZO SCHOOL OF LAW": "Cardozo, Yeshiva University",
    "CHICAGO-KENT COLLEGE OF LAW-IIT": "Chicago-Kent, Illinois Institute of Technology",
    "CITY UNIVERSITY OF NEW YORK": "City University of New York, University of",
    "DISTRICT OF COLUMBIA": "District of Columbia, University of",
    "LEWIS AND CLARK COLLEGE": "Lewis & Clark Law School",
    "LINCOLN MEMORIAL": "Lincoln Memorial University",
    "MCGEORGE SCHOOL OF LAW": "Pacific, University of the",
    "MISSISSIPPI COLLEGE": "Mississippi Christian University",
    "MITCHELL|HAMLINE": "Mitchell/Hamline School of Law",
    "PONTIFICAL CATHOLIC UNIVERSITY OF P.R.": "Pontifical Catholic University of Puerto Rico",
    "SOUTHERN ILLINOIS UNIVERSITY-CARBONDALE": "Southern Illinois University",
    "ST. THOMAS UNIVERSITY (FLORIDA)": "St. Thomas University (Miami)",
    "ST. THOMAS, UNIVERSITY OF (MINNESOTA)": "St. Thomas, (Minneapolis) University of",
    "TEXAS AT AUSTIN, UNIVERSITY OF": "Texas, University of",
    "UNIVERSITY OF BUFFALO-SUNY": "Buffalo, University at",
    "UNIVERSITY OF CALIFORNIA COLLEGE OF THE LAW, SAN FRANCISCO": "California-San Francisco, University of",
    "UNIVERSITY OF ILLINOIS CHICAGO SCHOOL OF LAW": "Illinois-Chicago, University of",
    "UNIVERSITY OF MASSACHUSETTS DARTMOUTH": "Massachusetts/Dartmouth, University of",
    "UNIVERSITY OF NEVADA - LAS VEGAS": "Nevada-Las Vegas, University of",
    "UNT DALLAS COLLEGE OF LAW": "North Texas at Dallas, University of",
    "WASHINGTON UNIVERSITY": "Washington University (St. Louis)",
    "WESTERN MICHIGAN UNIVERSITY": "Cooley Law School",  # WMU-Cooley, 2016-2021; class 411 then 277
    "COOLEY LAW SCHOOL": "Cooley Law School",
    "WESTERN STATE COLLEGE OF LAW": "Western State, Westcliff University",
    "WIDENER UNIVERSITY-DELAWARE": "Widener University Delaware Law School",
    "WIDENER-COMMONWEALTH": "Widener University Commonwealth Law School",
    "WILLIAM AND MARY LAW SCHOOL": "William & Mary",
}


def school_key(name: str) -> str:
    """One stable key per institution across report years: current name, no leading "The"."""
    name = NAME_ALIASES.get(name.strip(), name.strip())
    return re.sub(r"(^|-)the(-|$)", "-", slug(name)).strip("-")


def sheet_year(sheet_name: str) -> int:
    m = re.match(r"(\d{4})_", sheet_name)
    if not m:
        raise ValueError(f"cannot read a year from sheet name {sheet_name!r}")
    return int(m.group(1))


def _n(row: dict, key: str | None) -> int:
    v = row.get(key) if key else None
    return int(v) if isinstance(v, (int, float)) else 0


# The ABA renamed columns over the years: 2024-25 end in "Total", 2020-23 in "Number", and
# 2016-19 also renamed a few categories. Each concept lists its names, newest first. A concept
# marked optional may be absent in some years (e.g. "law school funded" is not in 2016-18).
ALIASES: dict[str, tuple[bool, list[str]]] = {
    "grads": (True, ["Total_GraduatesTotal", "Total_GraduatesNumber"]),
    "bar_ftlt": (True, ["Employed_BarAdmissionRequiredFTLT", "Employed_BarPassageRequiredFTLT"]),
    "jd_ftlt": (True, ["Employed_JDAdvantageFTLT"]),
    "bar_total": (True, ["Employed_BarAdmissionRequiredTotal", "Employed_BarPassageRequiredNumber"]),
    "jd_total": (True, ["Employed_JDAdvantageTotal", "Employed_JDAdvantageNumber"]),
    "profession": (True, ["Employed_ProfessionPositionTotal", "Employed_ProfessionPositionNumber"]),
    "other_position": (True, ["Employed_OtherPositionTotal", "Employed_OtherPositionNumber",
                              "Employed_NonProfessionPositionNumber"]),
    "undeterminable": (True, ["Employed_UndeterminableTotal", "Employed_UndeterminableNumber"]),
    "law_school": (False, ["Employed_LawSchoolTotal", "Employed_LawSchoolNumber"]),
    "grad_study": (True, ["EnrolledInGraduateStudiesTotal", "EnrolledInGraduateStudiesNumber",
                          "PursuingGraduateDegreeNumber"]),
    "deferred": (True, ["EmployedStartDateDeferredTotal", "EmployedStartDateDeferredNumber",
                        "UnEmployedStartDateDeferredNumber"]),
    "not_seeking": (True, ["UnEmployedNotSeekingTotal", "UnEmployedNotSeekingNumber"]),
    "seeking": (True, ["UnEmployedSeekingTotal", "UnEmployedSeekingNumber"]),
    "unknown": (True, ["EmploymentStatusUnknownTotal", "EmploymentStatusUnknownNumber"]),
    "biglaw": (True, ["501Plus-Total", "501-PLUS"]),
    "fed_clerkship": (True, ["Clerkships_Federal_Total", "Clerkships_Federal"]),
    "public_interest": (True, ["PublicInterest_Total", "PublicInterest"]),
    "government": (True, ["Government_Total", "Government"]),
    "business": (True, ["BusinessIndustry_Total", "BusinessIndustry"]),
}


def resolve_layout(columns) -> dict[str, str | None]:
    """Concept -> the column name this file uses. Raises (rather than guessing) if a required
    concept can't be found, so an unrecognized layout can never load as silent zeros."""
    cols = set(columns)
    layout, missing = {}, []
    for concept, (required, names) in ALIASES.items():
        found = next((n for n in names if n in cols), None)
        layout[concept] = found
        if required and found is None:
            missing.append(f"{concept} (looked for {', '.join(names)})")
    if missing:
        raise ValueError("unrecognized Employment Summary layout; missing: " + "; ".join(missing))
    return layout


# The 2024-25 names of the status buckets (used by tests to build rows in the newest layout).
STATUS_BUCKETS = [
    "Employed_BarAdmissionRequiredTotal", "Employed_JDAdvantageTotal", "Employed_ProfessionPositionTotal",
    "Employed_OtherPositionTotal", "Employed_UndeterminableTotal", "Employed_LawSchoolTotal",
    "EnrolledInGraduateStudiesTotal", "EmployedStartDateDeferredTotal", "UnEmployedNotSeekingTotal",
    "UnEmployedSeekingTotal", "EmploymentStatusUnknownTotal",
]

# Every employment-status bucket. They sum to Total_Graduates for every school in every year,
# which the loader verifies for each file and the pipeline's categories-must-sum rule re-checks.
STATUS_CONCEPTS = ["bar_total", "jd_total", "profession", "other_position", "undeterminable", "law_school",
                   "grad_study", "deferred", "not_seeking", "seeking", "unknown"]


def employment_record(row: dict, year: int, layout: dict | None = None) -> dict:
    """One school-year as a pipeline import record. The headline measure matches the project's:
    graduates in full-time, long-term, bar-passage-required jobs, over all graduates."""
    L = layout or resolve_layout(row.keys())
    grads = _n(row, L["grads"])
    bar = _n(row, L["bar_ftlt"])
    jd = _n(row, L["jd_ftlt"])
    unemployed = _n(row, L["seeking"]) + _n(row, L["not_seeking"])
    all_buckets = sum(_n(row, L[c]) for c in STATUS_CONCEPTS)
    other = all_buckets - bar - jd - unemployed  # everything else: part-time/short-term, other job types, grad study, unknown
    name = str(row["SchoolName"]).strip()
    return {
        "source": "aba", "school_name": name, "school_key": school_key(name), "grad_year": year,
        "grads": grads, "emp_unit": "count",
        "emp_bar_required": bar, "emp_jd_advantage": jd, "emp_other": other, "emp_unemployed": unemployed,
        "emp_biglaw": _n(row, L["biglaw"]), "emp_fed_clerkship": _n(row, L["fed_clerkship"]),
        "emp_public_interest": _n(row, L["public_interest"]), "emp_government": _n(row, L["government"]),
        "emp_business": _n(row, L["business"]),
        "notes": "",
    }


def _problems(records: list[dict]) -> tuple[list[str], list[str]]:
    zero = [r["school_name"] for r in records if r["grads"] <= 0]
    off = [r["school_name"] for r in records
           if r["emp_bar_required"] + r["emp_jd_advantage"] + r["emp_other"] + r["emp_unemployed"] != r["grads"]]
    return zero, off


def load_employment_file(path: Path) -> tuple[int, list[dict]]:
    """Reads one year. In some years (2016, 2021) the ABA reports law-school-funded jobs as a
    separate group that must be added to reach total graduates; in others they are already inside
    the other categories. So the standard layout is tried first, then the funded-jobs variant, and
    whichever makes every school's categories sum exactly to its graduates is used. If neither
    does, the file is refused rather than loaded with guessed numbers."""
    sheet, rows = read_xlsx(path)
    year = sheet_year(sheet)
    if not rows:
        raise ValueError(f"{path.name}: no data rows")
    base = resolve_layout(rows[0].keys())
    variants = [base]
    if base["law_school"] is None and "Funded_TotTotalEmployed" in rows[0]:
        variants.append({**base, "law_school": "Funded_TotTotalEmployed"})
    last = None
    for layout in variants:
        records = [employment_record(r, year, layout) for r in rows]
        zero, off = _problems(records)
        if not zero and not off:
            return year, records
        last = (zero, off)
    zero, off = last
    raise ValueError(f"{path.name}: {len(zero)} schools with no graduates and {len(off)} whose categories "
                     f"don't sum to graduates (e.g. {(zero + off)[:3]}); refusing to load a layout I misread")


# ---------------------------------------------------------------- per-school profile (admissions, cost, bar)

CREDITS_PER_YEAR = 30  # a standard full-time JD year (about 88 credits over three years)


def to_num(value) -> float | None:
    """'$22,359' -> 22359.0, '157' -> 157.0, 94 -> 94.0, blanks and 'N/A' -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
    if text in ("", "N/A", "n/a", "-", "NA"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_frac(value) -> float | None:
    """A percent given as '70.16%' or as a plain number 58.53 -> 0.7016 / 0.5853."""
    n = to_num(value)
    return None if n is None else round(n / 100, 4)


def _latest(data_dir: Path, pattern: str) -> tuple[Path, int] | None:
    best = None
    for p in data_dir.glob(pattern):
        m = re.search(r"_(\d{4})\.xlsx$", p.name)
        if m and (best is None or int(m.group(1)) > best[1]):
            best = (p, int(m.group(1)))
    return best


def _by_school(rows: list[dict], key: str) -> dict[str, dict]:
    return {str(r[key]).strip(): r for r in rows if r.get(key) and not str(r[key]).strip().startswith("*")}


def profile_flags(p: dict) -> list[str]:
    """The same kind of sanity rules the pipeline applies to simulated records."""
    flags = []
    l = [p.get("lsat_25"), p.get("lsat_50"), p.get("lsat_75")]
    g = [p.get("gpa_25"), p.get("gpa_50"), p.get("gpa_75")]
    for vals, name in ((l, "lsat"), (g, "gpa")):
        if None not in vals and not (vals[0] <= vals[1] <= vals[2]):
            flags.append(f"{name}_percentiles_out_of_order")
    for key in ("acceptance_rate", "bar_first_time_pass", "bar_two_year_pass", "grants_share"):
        v = p.get(key)
        if v is not None and not (0 <= v <= 1):
            flags.append(f"{key}_out_of_range")
    if p.get("tuition_resident") is not None and p["tuition_resident"] <= 0:
        flags.append("tuition_not_positive")
    return flags


def build_school_profiles(data_dir: Path) -> list[dict]:
    """One profile per school from the newest file of each kind in data_dir. Each profile records
    which edition (year) every group of fields came from."""
    kinds = {
        "basics": "The_Basics_*.xlsx", "fyc": "First_Year_Class_*.xlsx",
        "tuition": "Tuitions_and_Fees_*.xlsx", "grants": "Grants_and_Scholarships_*.xlsx",
        "bar1": "First_Time_Bar_*.xlsx", "bar2": "Two-Year_Ultimate_Bar_*.xlsx",
    }
    tables, editions = {}, {}
    for kind, pattern in kinds.items():
        found = _latest(data_dir, pattern)
        if not found:
            tables[kind], editions[kind] = {}, None
            continue
        path, year = found
        _, rows = read_xlsx(path)
        tables[kind] = _by_school(rows, "School Name" if kind.startswith("bar") else "SchoolName")
        editions[kind] = year

    names = sorted(set().union(*[set(t) for t in tables.values()]))
    profiles = []
    for name in names:
        b, f, t, g = (tables[k].get(name, {}) for k in ("basics", "fyc", "tuition", "grants"))
        b1, b2 = tables["bar1"].get(name, {}), tables["bar2"].get(name, {})
        tuition = to_num(t.get("FT_Resident_Annual"))
        tuition_nr = to_num(t.get("FT_NonResident_Annual"))
        fees = to_num(t.get("FTRS_AnnualFees"))
        basis = "annual"
        if not tuition:  # schools that bill per credit report $0 as an annual figure
            per_credit, per_credit_nr = to_num(t.get("FT_Resident_Credit")), to_num(t.get("FT_NonResident_Credit"))
            if per_credit:
                tuition, basis = per_credit * CREDITS_PER_YEAR, "per_credit_estimate"
                tuition_nr = per_credit_nr * CREDITS_PER_YEAR if per_credit_nr else None
                fees = to_num(t.get("FTRS_PerCredit_AnnualFees"))
        living = to_num(t.get("Living_Off_Campus"))
        two_key = next((k for k in b2 if k.endswith("Graduates") and k[:4].isdigit()), None)
        p = {
            "school_key": school_key(name), "school_name": name, "school_type": b.get("SchoolType"),
            "basics_edition": editions["basics"], "admissions_edition": editions["fyc"],
            "applications": to_num(f.get("Applications")), "offers": to_num(f.get("Offers")),
            "acceptance_rate": to_frac(f.get("AcceptanceRate")), "enrollees": to_num(f.get("Enrollees")),
            "lsat_25": to_num(f.get("All25thPercentileLSAT")), "lsat_50": to_num(f.get("All50thPercentileLSAT")),
            "lsat_75": to_num(f.get("All75thPercentileLSAT")),
            "gpa_25": to_num(f.get("All25thPercentileUGPA")), "gpa_50": to_num(f.get("All50thPercentileUGPA")),
            "gpa_75": to_num(f.get("All75thPercentileUGPA")),
            "cost_edition": editions["tuition"], "tuition_resident": tuition,
            "tuition_nonresident": tuition_nr, "tuition_basis": basis, "fees": fees, "living_off_campus": living,
            "grants_edition": editions["grants"],
            "grants_share": to_frac(g.get("Total Percentage # of Recieving Grants Total %")),
            "grant_median_ft": to_num(g.get("FT 50th percentile grant amount")),
            "full_tuition_share": to_frac(g.get("Full tuition total Percentage %")),
            "bar_edition": editions["bar1"], "bar_first_time_takers": to_num(b1.get("Total First Time Takers")),
            "bar_first_time_pass": to_frac(b1.get("AvgSchoolPassPercent*")),
            "bar_state_avg": to_frac(b1.get("AvgStatePassPercent**")),
            "bar_two_year_edition": editions["bar2"],
            "bar_two_year_pass": to_frac(b2.get("%Passers")),
        }
        p["est_net_tuition"] = estimated_net_tuition(p)
        p["flags"] = profile_flags(p)
        profiles.append(p)
    return profiles


def estimated_net_tuition(p: dict) -> float | None:
    """Sticker tuition + fees, less the expected grant: the share of students who receive a grant
    times the median full-time grant. An estimate of the average discount, not any one student's."""
    if p.get("tuition_resident") is None:
        return None
    sticker = p["tuition_resident"] + (p.get("fees") or 0)
    discount = (p.get("grants_share") or 0) * (p.get("grant_median_ft") or 0)
    return round(max(sticker - discount, 0), 2)
