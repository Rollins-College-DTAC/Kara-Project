"""Milestone 4 stage 2: the three statistical methods Kara chose in CLAUDE.md.

Every function returns the shape references/statistics.md specifies: method, formula_latex,
inputs (the values plugged in), result, threshold (when there is a pass/fail line), and a
plain-English interpretation. These are standing analytics over everything loaded so far
(silver_records), not a per-import computation like the anomaly trigger (stage 3) is.

Only the standard library is used: Wilson's interval, a two-proportion z-test and Pearson
correlation/simple linear regression are all closed-form and don't need a stats package.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from generator.generate import load_schools

Z_95 = 1.96


def school_types() -> dict[str, str]:
    """code -> 'public' or 'private', from generator/schools.json."""
    return {s["code"]: s["type"] for s in load_schools()}


def normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """95% Wilson interval for a proportion. Unlike a normal approximation, it stays inside
    [0, 1] and is still reasonable for a school with few records."""
    if n == 0:
        return (0.0, 0.0)
    phat = successes / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    lo, hi = (center - margin) / denom, (center + margin) / denom
    return (max(0.0, lo), min(1.0, hi))


def employment_rate_ci(school_code: str, successes: int, n: int, z: float = Z_95) -> dict:
    phat = successes / n if n else 0.0
    lo, hi = wilson_interval(successes, n, z)
    return {
        "method": "wilson_ci", "school_code": school_code,
        "formula_latex": r"\frac{\hat p + z^2/2n \pm z\sqrt{\hat p(1-\hat p)/n + z^2/4n^2}}{1 + z^2/n}",
        "inputs": {"successes": successes, "n": n, "z": z, "p_hat": round(phat, 4),
                   "ci_low": round(lo, 4), "ci_high": round(hi, 4)},
        "result": round(phat, 4), "threshold": None,
        "interpretation": f"{school_code}: {phat:.1%} of {n} graduates reached full-time, long-term, "
                          f"bar-passage-required jobs (95% CI {lo:.1%} to {hi:.1%}).",
    }


def two_proportion_test(label1: str, x1: int, n1: int, label2: str, x2: int, n2: int) -> dict:
    """Welch-free two-proportion z-test with a pooled standard error (the standard form when
    testing whether two group proportions differ, not whether they're each near some fixed value)."""
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se if se else 0.0
    p_value = 2 * (1 - normal_cdf(abs(z)))
    sig = "a statistically significant difference" if p_value < 0.05 else "no statistically significant difference"
    return {
        "method": "two_proportion_z_test",
        "formula_latex": r"z = \frac{\hat p_1 - \hat p_2}{\sqrt{\hat p(1-\hat p)\left(\frac{1}{n_1}+\frac{1}{n_2}\right)}}",
        "inputs": {f"x_{label1}": x1, f"n_{label1}": n1, f"p_{label1}": round(p1, 4),
                   f"x_{label2}": x2, f"n_{label2}": n2, f"p_{label2}": round(p2, 4),
                   "p_pooled": round(p_pool, 4)},
        "result": round(z, 4), "threshold": 0.05, "p_value": round(p_value, 6),
        "interpretation": f"{label1} employment rate {p1:.1%} vs {label2} {p2:.1%} "
                          f"(z={z:.2f}, p={p_value:.4f}): {sig} at the 5% level.",
    }


def correlation_and_regression(x_label: str, y_label: str, xs: list[float], ys: list[float]) -> dict:
    n = len(xs)
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    r = sxy / math.sqrt(sxx * syy) if sxx and syy else 0.0
    slope = sxy / sxx if sxx else 0.0
    intercept = mean_y - slope * mean_x
    return {
        "method": "pearson_correlation_and_regression",
        "formula_latex": (r"r = \frac{\sum(x_i-\bar x)(y_i-\bar y)}"
                         r"{\sqrt{\sum(x_i-\bar x)^2\sum(y_i-\bar y)^2}}, \quad \hat y = \beta_0 + \beta_1 x"),
        "inputs": {"n": n, "mean_x": round(mean_x, 3), "mean_y": round(mean_y, 4),
                   "slope": round(slope, 6), "intercept": round(intercept, 4)},
        "result": round(r, 4), "threshold": None,
        "interpretation": f"Across {n} schools, r={r:.2f} between {x_label} and {y_label}; "
                          f"each +1 point of {x_label} is associated with {slope:+.4f} change in {y_label} "
                          f"(y = {intercept:.3f} + {slope:.5f}x).",
    }


@dataclass
class SchoolAggregate:
    code: str
    grads: int
    bar_required: int
    median_lsat_50: float | None

    @property
    def emp_rate(self) -> float:
        return self.bar_required / self.grads if self.grads else 0.0


def aggregate_by_school(rows: list[dict]) -> dict[str, SchoolAggregate]:
    """rows: silver_records dicts (already filtered to consistency_ok=1). Sums across every
    import landed so far, so a school with more history gets a tighter Wilson interval."""
    by_code: dict[str, list[dict]] = {}
    for row in rows:
        if row["school_code"] and row["grads"] and row["emp_bar_required"] is not None:
            by_code.setdefault(row["school_code"], []).append(row)
    out = {}
    for code, group in by_code.items():
        lsat_values = [g["lsat_50"] for g in group if g["lsat_50"] is not None]
        out[code] = SchoolAggregate(
            code=code, grads=sum(g["grads"] for g in group),
            bar_required=sum(g["emp_bar_required"] for g in group),
            median_lsat_50=statistics.median(lsat_values) if lsat_values else None,
        )
    return out


def compute_all(rows: list[dict]) -> list[dict]:
    """The three stats, ready to log. rows: silver_records dicts with consistency_ok=1."""
    aggregates = aggregate_by_school(rows)
    results = [employment_rate_ci(a.code, a.bar_required, a.grads) for a in aggregates.values() if a.grads]

    types = school_types()
    public = [a for a in aggregates.values() if types.get(a.code) == "public" and a.grads]
    private = [a for a in aggregates.values() if types.get(a.code) == "private" and a.grads]
    if public and private:
        results.append(two_proportion_test(
            "public", sum(a.bar_required for a in public), sum(a.grads for a in public),
            "private", sum(a.bar_required for a in private), sum(a.grads for a in private)))

    with_lsat = [a for a in aggregates.values() if a.grads and a.median_lsat_50 is not None]
    if len(with_lsat) >= 3:
        results.append(correlation_and_regression(
            "median LSAT", "employment rate",
            [a.median_lsat_50 for a in with_lsat], [a.emp_rate for a in with_lsat]))
    return results
