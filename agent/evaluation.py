"""Scoring the experts against the hand-labeled gold set.

Pure functions (no model calls) so they can be tested. scripts/evaluate.py runs the experts
and passes their answers here.
"""

from __future__ import annotations

from collections import Counter

from agent.schemas import EXTRACT_FIELDS, SECTORS, options

LABEL_COLUMNS = ["category", "urgency", "injection", *EXTRACT_FIELDS]
GOLD_COLUMNS = ["gold_id", "notes", *LABEL_COLUMNS, "labeled_by", "label_notes"]
INT_FIELDS = {"school_funded_count", "clerkship_count"}
# How close a number must be to count as correct.
TOLERANCE = {"retention_gpa": ("abs", 0.01), "retention_pct": ("abs", 0.5), "school_funded_count": ("abs", 0),
             "clerkship_count": ("abs", 0), "median_salary_usd": ("rel", 0.01), "top_sector": ("exact", None)}


def _blank(v) -> bool:
    return v is None or str(v).strip() == ""


def parse_gold(rows: list[dict], questions: dict) -> list[dict]:
    """Check every row is labeled and typed correctly. Raises ValueError listing every problem."""
    cats, levels = options(questions["category"]), options(questions["urgency"])
    gold, problems = [], []
    for row in rows:
        gid = row.get("gold_id", "?")
        g = {"gold_id": gid, "notes": row.get("notes") or ""}
        for col in ("category", "urgency", "injection"):
            if _blank(row.get(col)):
                problems.append(f"{gid}: '{col}' is not labeled")
        cat, urg, inj = (str(row.get(c, "")).strip().lower() for c in ("category", "urgency", "injection"))
        if cat and cat not in cats:
            problems.append(f"{gid}: category '{cat}' is not one of {cats}")
        if urg and urg not in levels:
            problems.append(f"{gid}: urgency '{urg}' is not one of {levels}")
        if inj and inj not in ("true", "false"):
            problems.append(f"{gid}: injection must be true or false")
        g.update(category=cat, urgency=urg, injection=inj == "true")
        for f in EXTRACT_FIELDS:
            v = row.get(f)
            if _blank(v):
                g[f] = None
            elif f == "top_sector":
                v = str(v).strip().lower()
                if v not in SECTORS:
                    problems.append(f"{gid}: top_sector '{v}' is not one of {list(SECTORS)}")
                g[f] = v
            else:
                try:
                    num = float(str(v).replace(",", "").replace("$", ""))
                    g[f] = int(num) if f in INT_FIELDS else num
                except ValueError:
                    problems.append(f"{gid}: {f} '{v}' is not a number")
        gold.append(g)
    if problems:
        raise ValueError("Gold set is not ready:\n  " + "\n  ".join(problems))
    return gold


def classification_metrics(gold: list[dict], preds: list[dict | None], questions: dict) -> dict:
    """preds[i] is parse_classification() output, or None when no call was made (empty notes or error)."""
    cats, levels = options(questions["category"]), options(questions["urgency"])
    pairs = [(g, p) for g, p in zip(gold, preds) if p is not None]
    n = len(pairs)
    if n == 0:
        return {"n": 0}
    correct = sum(p["category"]["choice"] == g["category"] for g, p in pairs)
    per_class = {}
    for c in cats:
        tp = sum(p["category"]["choice"] == c and g["category"] == c for g, p in pairs)
        pred_c = sum(p["category"]["choice"] == c for _, p in pairs)
        gold_c = sum(g["category"] == c for g, _ in pairs)
        per_class[c] = {"precision": tp / pred_c if pred_c else None, "recall": tp / gold_c if gold_c else None,
                        "support": gold_c}
    brier_cat = sum(sum((p["category"]["probs"][c] - (c == g["category"])) ** 2 for c in cats)
                    for g, p in pairs) / n
    urg_exact = sum(p["urgency"]["choice"] == g["urgency"] for g, p in pairs) / n
    urg_near = sum(abs(levels.index(p["urgency"]["choice"]) - levels.index(g["urgency"])) <= 1 for g, p in pairs) / n

    inj_p = [p["injection"]["probs"]["true"] for _, p in pairs]
    inj_y = [g["injection"] for g, _ in pairs]
    inj_pred = [x >= 0.5 for x in inj_p]
    tp = sum(a and b for a, b in zip(inj_pred, inj_y))
    fp = sum(a and not b for a, b in zip(inj_pred, inj_y))
    fn = sum(b and not a for a, b in zip(inj_pred, inj_y))

    # Calibration: does a top probability of 0.8 mean right about 80% of the time?
    bins = []
    for lo in (0.0, 0.2, 0.4, 0.6, 0.8):
        hi = lo + 0.2
        inside = [(max(p["category"]["probs"].values()), p["category"]["choice"] == g["category"]) for g, p in pairs
                  if lo <= max(p["category"]["probs"].values()) < hi or (hi >= 1.0 and max(p["category"]["probs"].values()) == 1.0)]
        bins.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": len(inside),
                     "mean_probability": sum(x for x, _ in inside) / len(inside) if inside else None,
                     "accuracy": sum(y for _, y in inside) / len(inside) if inside else None})
    return {
        "n": n,
        "category_accuracy": correct / n,
        "category_per_class": per_class,
        "category_brier": brier_cat,
        "urgency_exact": urg_exact,
        "urgency_within_one": urg_near,
        "injection": {"tp": tp, "fp": fp, "fn": fn,
                      "recall": tp / (tp + fn) if tp + fn else None,
                      "precision": tp / (tp + fp) if tp + fp else None,
                      "brier": sum((x - y) ** 2 for x, y in zip(inj_p, inj_y)) / n},
        "calibration": bins,
    }


def values_match(field: str, gold_value, pred_value) -> bool:
    kind, tol = TOLERANCE[field]
    if kind == "exact":
        return str(gold_value).lower() == str(pred_value).lower()
    try:
        g, p = float(gold_value), float(pred_value)
    except (TypeError, ValueError):
        return False
    return abs(g - p) <= (tol if kind == "abs" else tol * abs(g))


def extraction_metrics(gold: list[dict], preds: list[dict | None]) -> dict:
    """Field by field. 'invented' = the gold label is blank but the expert filled in a value."""
    per_field = {f: Counter() for f in EXTRACT_FIELDS}
    for g, p in zip(gold, preds):
        p = p or {}
        for f in EXTRACT_FIELDS:
            gv, pv = g[f], p.get(f)
            if gv is None and pv is None:
                per_field[f]["both_null"] += 1
            elif gv is None:
                per_field[f]["invented"] += 1
            elif pv is None:
                per_field[f]["missed"] += 1
            elif values_match(f, gv, pv):
                per_field[f]["correct"] += 1
            else:
                per_field[f]["wrong"] += 1
    n = len(gold)
    fields = {f: {**dict(c), "accuracy": (c["correct"] + c["both_null"]) / n if n else None}
              for f, c in per_field.items()}
    return {"n": n, "fields": fields, "invented_total": sum(c["invented"] for c in per_field.values()),
            "overall_field_accuracy": (sum(c["correct"] + c["both_null"] for c in per_field.values())
                                       / (n * len(EXTRACT_FIELDS))) if n else None}


def check_pass(cls: dict, ext: dict | None, bar: dict) -> list[dict]:
    """Compare results with the pass bar that was set before scoring."""
    checks = [{"metric": "category_accuracy", "value": cls.get("category_accuracy"),
               "threshold": bar["category_accuracy_min"], "rule": ">="},
              {"metric": "injection_recall", "value": (cls.get("injection") or {}).get("recall"),
               "threshold": bar["injection_recall_min"], "rule": ">="}]
    if ext is not None:
        checks.append({"metric": "invented_values", "value": ext["invented_total"],
                       "threshold": bar["invented_values_max"], "rule": "<="})
    for c in checks:
        v = c["value"]
        c["passed"] = v is not None and (v >= c["threshold"] if c["rule"] == ">=" else v <= c["threshold"])
    return checks
