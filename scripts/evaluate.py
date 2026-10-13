"""Score the experts on the hand-labeled gold set.

Runs classification with every available expert (Jev if wired, Claude Haiku if a key is set,
rules always) and extraction with Haiku and rules. Every call goes through the Gateway, so it
is cached, capped and written to model_usage_log. Results are compared with the pass bar in
config.toml (set before scoring), written to docs/eval/ and to the eval_log table.

Usage:
  python scripts/evaluate.py              # all available experts (needs ANTHROPIC_API_KEY in .env for Haiku)
  python scripts/evaluate.py --offline    # rules only, no API calls, free
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import ROOT, load_agent_config  # noqa: E402
from agent.db import connect  # noqa: E402
from agent.evaluation import check_pass, classification_metrics, extraction_metrics, parse_gold  # noqa: E402
from agent.experts import build_experts  # noqa: E402
from agent.gateway import Gateway, InvalidAnswer, short  # noqa: E402
from agent.redact import note_text, redact  # noqa: E402
from agent.schemas import Extraction, load_questions, parse_classification  # noqa: E402
from agent.sql import RunContext, now_iso  # noqa: E402


def run_evaluation(cfg: dict, gold_path: Path, experts: dict, offline: bool = False, out_dir: Path | None = None) -> dict:
    mcfg = {**cfg["models"], "max_tokens_per_run": cfg["evaluation"]["max_tokens"]}
    questions = load_questions(mcfg["questions_path"])
    qver = Path(mcfg["questions_path"]).stem
    template = Path(mcfg["extract_prompt_path"]).read_text(encoding="utf-8")
    pver = Path(mcfg["extract_prompt_path"]).stem
    with open(gold_path, newline="", encoding="utf-8") as f:
        gold = parse_gold(list(csv.DictReader(f)), questions)

    conn = connect(cfg["sqlite_path"])
    ctx = RunContext(conn=conn, run_id=f"eval-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}", file_name=gold_path.name)
    gw = Gateway(ctx, mcfg, experts)
    texts = [redact(note_text(g["notes"])) for g in gold]

    classify_experts = ["rules"] if offline else \
        [e for e in ("jev", "haiku") if experts[e].available()] + ["rules"]
    extract_experts = ["rules"] if offline else (["haiku"] if experts["haiku"].available() else []) + ["rules"]

    results: dict = {"run_id": ctx.run_id, "evaluated_at": now_iso(), "n_gold": len(gold),
                     "questions_version": qver, "prompt_version": pver, "classify": {}, "extract": {}, "errors": []}
    latencies: dict[str, list[int]] = {}

    for name in classify_experts:
        preds = []
        for g, (text, pii) in zip(gold, texts):
            if not text:
                preds.append(None)
                continue
            try:
                res, parsed = gw.call("evaluate", "classify", name, qver, text,
                                      lambda e, t=text: e.classify(t, questions),
                                      lambda d: parse_classification(questions, d))
                gw.log("evaluate", "classify", name, "evaluation: gold set", qver, result=res,
                       confidence=parsed["category"]["confidence"], outcome="valid", pii=pii)
                if not res.cached:
                    latencies.setdefault(res.model, []).append(res.latency_ms)
                preds.append(parsed)
            except Exception as exc:
                preds.append(None)
                results["errors"].append(f"classify {name} {g['gold_id']}: {short(exc)}")
        results["classify"][name] = classification_metrics(gold, preds, questions)
        results["classify"][name]["predictions"] = [
            {"gold_id": g["gold_id"], "category": p["category"]["choice"] if p else None,
             "p_max": round(max(p["category"]["probs"].values()), 3) if p else None,
             "injection_p": round(p["injection"]["probs"]["true"], 3) if p else None}
            for g, p in zip(gold, preds)]

    # Extraction is scored on non-injection records (injections are quarantined, never extracted).
    ext_gold = [(g, t) for g, t in zip(gold, texts) if not g["injection"]]
    for name in extract_experts:
        preds, invalid = [], 0
        for g, (text, pii) in ext_gold:
            if not text:
                preds.append(None)
                continue
            try:
                res, parsed = gw.call("evaluate", "extract", name, pver, text,
                                      lambda e, t=text: e.extract(t, template), Extraction.model_validate)
                gw.log("evaluate", "extract", name, "evaluation: gold set", pver, result=res,
                       confidence=1.0 if parsed.confidence == "high" else 0.0, outcome="valid", pii=pii)
                if not res.cached:
                    latencies.setdefault(res.model, []).append(res.latency_ms)
                preds.append(parsed.model_dump())
            except InvalidAnswer as exc:
                invalid += 1
                preds.append(None)
                results["errors"].append(f"extract {name} {g['gold_id']}: invalid: {short(exc.error)}")
            except Exception as exc:
                preds.append(None)
                results["errors"].append(f"extract {name} {g['gold_id']}: {short(exc)}")
        results["extract"][name] = {**extraction_metrics([g for g, _ in ext_gold], preds), "invalid_answers": invalid}

    results["latency_ms_by_expert"] = {m: {"calls": len(v), "mean": statistics.mean(v), "median": statistics.median(v)}
                                       for m, v in latencies.items() if v}
    primary_cls = next(e for e in ("jev", "haiku", "rules") if e in results["classify"])
    primary_ext = next((e for e in ("haiku", "rules") if e in results["extract"]), None)
    results["primary"] = {"classify": primary_cls, "extract": primary_ext}
    results["pass_bar"] = check_pass(results["classify"][primary_cls],
                                     results["extract"].get(primary_ext), cfg["evaluation"])
    results["tokens_used"] = gw.run_tokens

    # eval_log: every score with the questions and prompt versions.
    eval_id = f"ev-{uuid.uuid4().hex[:8]}"
    for check in results["pass_bar"]:
        expert = primary_ext if check["metric"] == "invented_values" else primary_cls
        conn.execute("INSERT INTO eval_log (eval_id, evaluated_at, expert, metric, value, threshold, passed, "
                     "questions_version, prompt_version, n_records) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (eval_id, results["evaluated_at"], expert, check["metric"], check["value"], check["threshold"],
                      int(check["passed"]), qver, pver, len(gold)))
    for name, m in results["classify"].items():
        for metric in ("category_accuracy", "category_brier", "urgency_exact"):
            if metric in m:
                conn.execute("INSERT INTO eval_log (eval_id, evaluated_at, expert, metric, value, questions_version, "
                             "prompt_version, n_records) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (eval_id, results["evaluated_at"], name, metric, m[metric], qver, pver, m["n"]))
    conn.commit()
    conn.close()

    out_dir = out_dir or ROOT / "docs" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{ctx.run_id}.json"
    out_file.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    results["output_file"] = str(out_file)
    return results


def print_summary(r: dict) -> None:
    print(f"\nGold set: {r['n_gold']} records | questions {r['questions_version']} | prompt {r['prompt_version']}")
    for name, m in r["classify"].items():
        if m.get("n"):
            inj = m["injection"]
            print(f"  classify {name:6s} n={m['n']:2d}  category acc {m['category_accuracy']:.0%}  "
                  f"Brier {m['category_brier']:.3f}  urgency exact {m['urgency_exact']:.0%}  "
                  f"injection recall {inj['recall'] if inj['recall'] is None else f'{inj['recall']:.0%}'}")
    for name, m in r["extract"].items():
        print(f"  extract  {name:6s} n={m['n']:2d}  field acc {m['overall_field_accuracy']:.0%}  "
              f"invented {m['invented_total']}  invalid answers {m['invalid_answers']}")
    for model, lat in r["latency_ms_by_expert"].items():
        print(f"  latency  {model}: mean {lat['mean']:.0f} ms over {lat['calls']} calls")
    print("\nPass bar (set before scoring):")
    for c in r["pass_bar"]:
        print(f"  {'PASS' if c['passed'] else 'FAIL'}  {c['metric']} = {c['value']}  (needs {c['rule']} {c['threshold']})")
    if r["errors"]:
        print(f"\n{len(r['errors'])} errors, first few:")
        for e in r["errors"][:5]:
            print("  " + e)
    print(f"\nTokens used: {r['tokens_used']}. Full results: {r['output_file']}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--gold", default=str(ROOT / "gold_set.csv"))
    p.add_argument("--offline", action="store_true", help="rules only, no API calls")
    args = p.parse_args()
    cfg = load_agent_config()
    try:
        results = run_evaluation(cfg, Path(args.gold), build_experts(cfg["models"]), offline=args.offline)
    except ValueError as exc:
        raise SystemExit(str(exc))
    print_summary(results)


if __name__ == "__main__":
    main()
