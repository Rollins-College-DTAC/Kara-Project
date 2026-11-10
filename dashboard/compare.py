"""Pure helpers for the Compare Schools page: per-school profile aggregation and a simple
employment-value index (outcome relative to estimated net cost). No Streamlit import, so
this is testable without running the app.

The "value" here is intentionally a rough, illustrative measure, not a real net-price or ROI
calculation: cost_of_attendance is an invented sticker price (no real financial-aid modeling),
and scholarship_share is the *share of the class* with merit aid, not each student's actual
discount. There is no real salary or debt data behind it.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


EMP_CATEGORIES = {"bar_required": "emp_bar_required", "jd_advantage": "emp_jd_advantage",
                  "other": "emp_other", "unemployed": "emp_unemployed"}


@dataclass
class SchoolProfile:
    code: str
    name: str | None
    n: int
    class_size: float | None
    acceptance_rate: float | None
    lsat_50: float | None
    gpa_50: float | None
    scholarship_share: float | None
    cost_of_attendance: float | None
    bar_pass_rate: float | None
    emp_rate: float | None
    emp_breakdown: dict | None = None  # share of grads in each employment category (sums to ~1)

    @property
    def est_net_cost(self) -> float | None:
        if self.cost_of_attendance is None or self.scholarship_share is None:
            return None
        return round(self.cost_of_attendance * (1 - self.scholarship_share), 2)

    @property
    def value_index(self) -> float | None:
        """Employment rate per $10,000 of estimated net cost. Higher = more employment outcome
        per dollar by this rough measure; says nothing about salary or career satisfaction."""
        net = self.est_net_cost
        if net is None or net <= 0 or self.emp_rate is None:
            return None
        return round(self.emp_rate / (net / 10000), 4)


def _mean(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.fmean(vals), 4) if vals else None


def build_school_profiles(rows: list[dict]) -> dict[str, SchoolProfile]:
    """rows: silver_records dicts. Pass only the rows you want averaged in (e.g. status='published'
    for a fair comparison of what's actually live)."""
    by_code: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("school_code"):
            by_code.setdefault(row["school_code"], []).append(row)

    profiles = {}
    for code, group in by_code.items():
        grads_total = sum(g["grads"] for g in group if g.get("grads"))
        bar_total = sum(g["emp_bar_required"] for g in group if g.get("emp_bar_required") is not None)
        emp_rate = round(bar_total / grads_total, 4) if grads_total else None
        breakdown = None
        if grads_total:
            breakdown = {key: round(sum(g.get(col) or 0 for g in group) / grads_total, 4)
                         for key, col in EMP_CATEGORIES.items()}
        profiles[code] = SchoolProfile(
            code=code, name=next((g["school_name"] for g in group if g.get("school_name")), None),
            n=len(group),
            class_size=_mean([g.get("class_size") for g in group]),
            acceptance_rate=_mean([g.get("acceptance_rate") for g in group]),
            lsat_50=_mean([g.get("lsat_50") for g in group]),
            gpa_50=_mean([g.get("gpa_50") for g in group]),
            scholarship_share=_mean([g.get("scholarship_share") for g in group]),
            cost_of_attendance=_mean([g.get("cost_of_attendance") for g in group]),
            bar_pass_rate=_mean([g.get("bar_pass_rate") for g in group]),
            emp_rate=emp_rate, emp_breakdown=breakdown,
        )
    return profiles


def rank_by_lsat(profiles: dict[str, SchoolProfile]) -> dict[str, int]:
    """A SAMPLE rank (1 = highest median LSAT, ties broken by employment rate). It is not a real
    publication's ranking -- these schools are fictional."""
    order = sorted(profiles, key=lambda c: (-(profiles[c].lsat_50 or 0), -(profiles[c].emp_rate or 0), c))
    return {code: i + 1 for i, code in enumerate(order)}


def admission_odds(lsat: float, gpa: float | None, school_lsat: float | None,
                   school_gpa: float | None) -> str | None:
    """Illustrative Safe / Target / Reach label comparing an applicant to a school's medians.
    Not a real admissions model: it only measures distance from the medians."""
    if school_lsat is None:
        return None
    parts = [(lsat - school_lsat) / 3.0]
    if gpa is not None and school_gpa is not None:
        parts.append((gpa - school_gpa) / 0.15)
    score = sum(parts) / len(parts)
    if score >= 0.75:
        return "Safe"
    if score >= -0.5:
        return "Target"
    return "Reach"
