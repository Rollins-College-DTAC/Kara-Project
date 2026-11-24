"""SAMPLE application tracking for the Compare Schools page: status, deadlines and a scholarship
offer per school. Entirely invented and deterministic (seeded by school code), generated on the
fly rather than stored -- this is demo data for the dashboard design, not part of the pipeline
and not anyone's real application record. No Streamlit import, so it's testable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

STATUSES = ["Draft", "Submitted", "Accepted", "Waitlisted"]

# Which deadlines still matter at each stage of an application.
RELEVANT = {
    "Draft": ["Application", "FAFSA"],
    "Submitted": ["FAFSA"],
    "Accepted": ["Seat deposit", "FAFSA"],
    "Waitlisted": ["FAFSA"],
}


@dataclass
class Deadline:
    label: str
    due: date


@dataclass
class Application:
    code: str
    status: str
    deadlines: list[Deadline] = field(default_factory=list)
    scholarship_offer: float | None = None


def sample_application(code: str, cost_of_attendance: float | None, today: date) -> Application:
    rng = random.Random(f"application:{code}")
    status = rng.choice(STATUSES)
    offsets = {"Application": rng.randint(4, 60), "FAFSA": rng.randint(8, 45),
               "Seat deposit": rng.randint(20, 110)}
    deadlines = sorted((Deadline(label, today + timedelta(days=offsets[label])) for label in RELEVANT[status]),
                       key=lambda d: d.due)
    offer = None
    if status in ("Accepted", "Waitlisted") and cost_of_attendance:
        offer = round(cost_of_attendance * rng.uniform(0.10, 0.60), -2)
    return Application(code=code, status=status, deadlines=deadlines, scholarship_offer=offer)


def upcoming_deadlines(apps: list[Application], today: date) -> list[tuple[date, str, str]]:
    """(due, label, school code), soonest first, future-dated only."""
    items = [(d.due, d.label, a.code) for a in apps for d in a.deadlines if d.due >= today]
    return sorted(items)


def deadline_urgency(days_left: int) -> str:
    if days_left <= 14:
        return "urgent"
    if days_left <= 30:
        return "soon"
    return "ok"
