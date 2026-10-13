"""Pydantic schemas: what a valid extraction looks like, and how classification answers are read."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SECTORS = ("small_firm", "large_firm", "government", "public_interest", "business_industry", "clerkship")


class Extraction(BaseModel):
    """Values pulled from one note. Anything not stated must be null."""
    model_config = ConfigDict(extra="forbid")

    retention_gpa: float | None = Field(None, ge=1.0, le=4.33)
    retention_pct: float | None = Field(None, ge=0, le=100)
    school_funded_count: int | None = Field(None, ge=0, le=1000)
    clerkship_count: int | None = Field(None, ge=0, le=1000)
    median_salary_usd: float | None = Field(None, ge=10_000, le=500_000)  # catches "95" meant as thousands
    top_sector: Literal[SECTORS] | None = None
    summary: str | None = Field(None, max_length=300)
    confidence: Literal["high", "low"]


EXTRACT_FIELDS = ["retention_gpa", "retention_pct", "school_funded_count", "clerkship_count",
                  "median_salary_usd", "top_sector"]


def load_questions(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def options(question: dict) -> list[str]:
    """Option names for a question: choice keys, score level names, or true/false."""
    if question["type"] == "choice":
        return list(question["criteria"])
    if question["type"] == "score":
        return [c.split(":", 1)[0].strip() for c in question["criteria"]]
    return ["true", "false"]


def choice_confidence(probs: dict[str, float]) -> float:
    """Confidence for a choice among n options: (p_max - 1/n) / (1 - 1/n). 0 = a coin toss, 1 = certain."""
    n = len(probs)
    p_max = max(probs.values())
    return max(0.0, (p_max - 1 / n) / (1 - 1 / n))


def _normalize(raw: dict, opts: list[str], name: str) -> dict[str, float]:
    if not isinstance(raw, dict) or set(raw) != set(opts):
        raise ValueError(f"{name}: expected probabilities for exactly {opts}")
    probs = {}
    for k in opts:
        v = raw[k]
        if not isinstance(v, (int, float)) or not 0 <= v <= 1:
            raise ValueError(f"{name}: probability for {k} must be between 0 and 1")
        probs[k] = float(v)
    total = sum(probs.values())
    if total <= 0:
        raise ValueError(f"{name}: probabilities sum to zero")
    return {k: v / total for k, v in probs.items()}


def parse_classification(questions: dict, data: dict) -> dict:
    """Turn an expert's answer into category, urgency and injection with probabilities and confidence.

    Expected shape (same for every expert):
      {"category": {"probabilities": {...}}, "urgency": {"probabilities": {...}},
       "injection": {"probability_true": 0.03}}
    """
    out: dict = {}
    for name, q in questions.items():
        answer = data.get(name)
        if answer is None:
            raise ValueError(f"missing answer for {name}")
        if q["type"] == "noul":
            p = answer.get("probability_true") if isinstance(answer, dict) else None
            if not isinstance(p, (int, float)) or not 0 <= p <= 1:
                raise ValueError(f"{name}: probability_true must be between 0 and 1")
            probs = {"true": float(p), "false": 1 - float(p)}
        else:
            probs = _normalize(answer.get("probabilities") if isinstance(answer, dict) else None, options(q), name)
        out[name] = {"choice": max(probs, key=probs.get), "probs": probs, "confidence": choice_confidence(probs)}
    return out
