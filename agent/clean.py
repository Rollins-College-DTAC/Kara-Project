"""Load step: clean and type the structured admissions/employment fields, then run the
per-record consistency checks CLAUDE.md describes.

This is separate from milestone 3's Validate step, which only checks Claude's extraction
from free text. Here we clean the record's own numeric columns (class size, LSAT, GPA,
employment counts, bar passage), independent of any model call.

Consistency rules match the generator's three seeded anomalies that are tagged
expected_detector="consistency_check" in generator_log.csv (never read by this code,
only used by tests and the answer-key scoring in the dashboard):
  - percentiles_out_of_order: a 25th percentile above the 50th, or 50th above the 75th
  - categories_dont_sum: the four employment categories don't add up to the grad count
  - counts_exceed_class: a single employment category exceeds the entire class size
A record that breaks any rule is held, never published, per the project's non-negotiable
rule that a person releases every held import.
"""

from __future__ import annotations

import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from generator.generate import DATE_FORMATS, load_schools

MISSING = {"", "n/a", "na", "none", "null"}
SUM_TOLERANCE = {"count": 0, "pct": 1.0}  # pct values are each independently rounded to 1 decimal


@lru_cache(maxsize=1)
def canonical_schools() -> dict[str, str]:
    """code ('LS-01', ...) -> canonical school name, from generator/schools.json."""
    return {s["code"]: s["name"] for s in load_schools()}


def canonical_code(raw: str | None) -> str | None:
    """Undo code_variant()'s dashes/case/whitespace mangling: 'ls07 ', 'LS7', '-LS-07' -> 'LS-07'."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    code = f"LS-{int(digits):02d}"
    return code if code in canonical_schools() else None


def is_missing(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in MISSING)


def parse_int(value) -> int | None:
    if is_missing(value):
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def parse_fraction(value) -> float | None:
    """A share written as a fraction (0.31) or a percent string ('31.0%')."""
    if is_missing(value):
        return None
    text = str(value).strip()
    try:
        if text.endswith("%"):
            return round(float(text[:-1]) / 100, 4)
        frac = float(text)
        return round(frac / 100, 4) if frac > 1 else round(frac, 4)
    except ValueError:
        return None


def parse_float(value) -> float | None:
    if is_missing(value):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def parse_date(value) -> str | None:
    """Try every format the generator can write; return ISO 'YYYY-MM-DD' or None."""
    if is_missing(value):
        return None
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def clean_record(raw: dict) -> dict:
    """Typed, cleaned fields plus consistency flags. Never raises: an unparseable value
    becomes None and is treated like any other missing value by the consistency checks."""
    code = canonical_code(raw.get("school_code"))
    class_size = parse_int(raw.get("class_size"))
    grads = parse_int(raw.get("grads"))
    unit = str(raw.get("emp_unit") or "").strip().lower()
    emp_raw = {k: parse_float(raw.get(k)) for k in
               ("emp_bar_required", "emp_jd_advantage", "emp_other", "emp_unemployed")}

    flags: list[str] = []
    if code is None:
        flags.append("unknown_school_code")

    # Employment counts: convert to a common unit (counts) when grads is known, so the
    # dashboard and statistics always read the same thing regardless of how the import unit it.
    emp_counts = dict(emp_raw)
    if unit == "pct" and grads is not None:
        emp_counts = {k: None if v is None else round(grads * v / 100) for k, v in emp_raw.items()}
    present = {k: v for k, v in emp_counts.items() if v is not None}
    if len(present) == 4 and grads is not None:
        total = sum(present.values())
        tolerance = SUM_TOLERANCE.get(unit, 0) if unit == "count" else SUM_TOLERANCE["pct"]
        if abs(total - grads) > tolerance:
            flags.append("categories_dont_sum")
    if class_size is not None and any(v is not None and v > class_size for v in present.values()):
        flags.append("counts_exceed_class")

    lsat = {k: parse_int(raw.get(k)) for k in ("lsat_25", "lsat_50", "lsat_75")}
    gpa = {k: parse_float(raw.get(k)) for k in ("gpa_25", "gpa_50", "gpa_75")}
    if None not in lsat.values() and not (lsat["lsat_25"] <= lsat["lsat_50"] <= lsat["lsat_75"]):
        flags.append("percentiles_out_of_order")
    if None not in gpa.values() and not (gpa["gpa_25"] <= gpa["gpa_50"] <= gpa["gpa_75"]):
        flags.append("percentiles_out_of_order")

    emp_rate = None
    if grads and emp_counts.get("emp_bar_required") is not None:
        emp_rate = round(emp_counts["emp_bar_required"] / grads, 4)

    return {
        "school_code": code, "school_name": canonical_schools().get(code) if code else None,
        "school_name_raw": raw.get("school_name"),
        "grad_year": parse_int(raw.get("grad_year")), "report_date": parse_date(raw.get("report_date")),
        "class_size": class_size, "grads": grads,
        "acceptance_rate": parse_fraction(raw.get("acceptance_rate")),
        "lsat_25": lsat["lsat_25"], "lsat_50": lsat["lsat_50"], "lsat_75": lsat["lsat_75"],
        "gpa_25": gpa["gpa_25"], "gpa_50": gpa["gpa_50"], "gpa_75": gpa["gpa_75"],
        "scholarship_share": parse_fraction(raw.get("scholarship_share")),
        "emp_bar_required": emp_counts["emp_bar_required"], "emp_jd_advantage": emp_counts["emp_jd_advantage"],
        "emp_other": emp_counts["emp_other"], "emp_unemployed": emp_counts["emp_unemployed"],
        "emp_rate": emp_rate, "bar_pass_rate": parse_fraction(raw.get("bar_pass_rate")),
        "consistency_ok": not flags, "consistency_flags": flags,
    }
