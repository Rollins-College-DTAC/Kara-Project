"""Rules: the deterministic fallback when the kill switch is on, the budget is spent or a model fails.

Keyword matching and regular expressions. Free, instant and predictable, but brittle,
which is exactly what the gold set will show.
"""

from __future__ import annotations

import re

from agent.experts.base import ExpertResult
from agent.schemas import options

KEYWORDS = {
    "scholarship_terms": ["scholarship", "renewal", "retain", "recipients", "merit award", "academic standing"],
    "funded_or_clerkship": ["school-funded", "clerkship", "fellowship"],
    "salary": ["salary", "salaries"],
    "bar_passage": ["bar pass", "bar passage", "takers", "bar exam"],
    "employment_narrative": ["placement", "employment narrative", "sector", "did well", "landed"],
}
INJECTION = re.compile(
    r"\b(ignore (all|any|the|previous)|system note|instruction|assistant[,:]|skip (all )?(checks|review|verification)|"
    r"without (human )?review|mark (this|it) (report )?as verified|rank (this|us) (school )?first)", re.I)
SECTOR_WORDS = {
    "small_firm": "small firm", "large_firm": "large firm", "government": "government",
    "public_interest": "public interest", "business_industry": "business and industry", "clerkship": "clerkship",
}


def _spread(opts: list[str], chosen: str, p: float) -> dict[str, float]:
    rest = (1 - p) / (len(opts) - 1)
    return {o: (p if o == chosen else rest) for o in opts}


class RulesExpert:
    name = "rules"
    model = "rules"

    def available(self) -> bool:
        return True

    def classify(self, text: str, questions: dict) -> ExpertResult:
        low = text.lower()
        hits = {cat: sum(k in low for k in kws) for cat, kws in KEYWORDS.items()}
        best = max(hits, key=hits.get)
        category = best if hits[best] > 0 else "other"
        urgency = {"scholarship_terms": "high", "salary": "high", "other": "low"}.get(category, "medium")
        data = {
            "category": {"probabilities": _spread(options(questions["category"]), category, 0.7)},
            "urgency": {"probabilities": _spread(options(questions["urgency"]), urgency, 0.6)},
            "injection": {"probability_true": 0.95 if INJECTION.search(text) else 0.02},
        }
        return ExpertResult(self.name, self.model, data)

    def extract(self, text: str, template: str | None = None) -> ExpertResult:
        def num(pattern):
            m = re.search(pattern, text, re.I)
            return float(m.group(1).replace(",", "")) if m else None

        gpa = num(r"(\d\.\d{1,2})\s*(?:cumulative\s+)?GPA") or num(r"GPA[^.]*?(\d\.\d{1,2})")
        pct = num(r"(\d{1,3}(?:\.\d)?)\s*(?:percent|%)\s+of\s+recipients")
        funded = num(r"(\d+)\s+graduates\s+held\s+school-funded")
        clerk = num(r"(\d+)\s+of\s+those\s+were\s+judicial\s+clerkships")
        salary_k = num(r"\$\s?(\d+(?:\.\d+)?)\s*[kK]\b")
        sector = next((key for key, words in SECTOR_WORDS.items()
                       if re.search(rf"strongest placement in {words}", text, re.I)), None)
        data = {
            "retention_gpa": gpa, "retention_pct": pct,
            "school_funded_count": int(funded) if funded is not None else None,
            "clerkship_count": int(clerk) if clerk is not None else None,
            "median_salary_usd": salary_k * 1000 if salary_k is not None else None,
            "top_sector": sector,
            "summary": text[:120] if text else None,
            "confidence": "low",  # rules can never vouch that a value was directly stated
        }
        return ExpertResult(self.name, self.model, data)
