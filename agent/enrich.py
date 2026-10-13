"""Steps 3 to 6 of the ETL loop: Redact, Route, Classify, Extract, Validate.

Each step writes a run_log row. Each model call writes a model_usage_log row.
What happens to a record:
  no notes                      -> status no_notes (no model call, no cost)
  injection probability high    -> quarantined + 'injection' incident (never acted on, never extracted)
  category confidence too low   -> review queue (a person decides)
  Haiku invalid or low confidence -> escalated to Sonnet; still invalid -> quarantined + incident
  otherwise                     -> extracted
The raw record in TinyDB is never changed.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from agent.experts import build_experts
from agent.gateway import Gateway, InvalidAnswer, short
from agent.redact import note_text, redact
from agent.router import route
from agent.schemas import Extraction, load_questions, parse_classification
from agent.sql import RunContext, now_iso, open_incident, run_sql, step


@dataclass
class Item:
    row_index: int
    text: str = ""
    pii: int = 0
    classification: dict | None = None
    classify_expert: str = ""
    extraction: dict | None = None
    extract_expert: str = ""
    escalate_reason: str | None = None
    status: str = ""
    reason: str = ""
    notes: list = field(default_factory=list)


def _validate_extraction(data: dict) -> Extraction:
    return Extraction.model_validate(data)


def _classify(gw: Gateway, it: Item, questions: dict, qver: str):
    """Classify one note: chosen expert, one retry on an invalid answer, then rules as the fallback."""
    r = route("classify", {"text": it.text}, gw.context())
    if r.reason.startswith("token budget"):
        gw.note_budget_reached()
    expert, reason, retried = r.expert, r.reason, False
    while True:
        try:
            res, parsed = gw.call("classify", "classify", expert, qver, it.text,
                                  lambda e: e.classify(it.text, questions),
                                  lambda d: parse_classification(questions, d))
            gw.log("classify", "classify", expert, reason, qver, result=res,
                   confidence=parsed["category"]["confidence"], outcome="valid", pii=it.pii, row_index=it.row_index)
            return parsed, expert
        except InvalidAnswer as exc:
            gw.log("classify", "classify", expert, f"{reason}; invalid: {short(exc.error)}", qver, result=exc.result,
                   outcome="retried" if not retried else "failed", pii=it.pii, row_index=it.row_index)
            if not retried and expert != "rules":
                retried, reason = True, f"retry after invalid answer ({r.reason})"
                continue
        except Exception as exc:  # unavailable, network or API error
            gw.log("classify", "classify", expert, f"{reason}; failed: {short(exc)}", qver,
                   outcome="failed", pii=it.pii, row_index=it.row_index)
        if expert == "rules":
            raise RuntimeError("rules classifier failed")
        expert, reason, retried = "rules", f"fallback: {expert} failed", False


def enrich(cfg: dict, ctx: RunContext, records: list[dict], experts: dict | None = None) -> dict:
    mcfg = cfg["models"]
    questions = load_questions(mcfg["questions_path"])
    qver = Path(mcfg["questions_path"]).stem
    template = Path(mcfg["extract_prompt_path"]).read_text(encoding="utf-8")
    pver = Path(mcfg["extract_prompt_path"]).stem
    gw = Gateway(ctx, mcfg, experts or build_experts(mcfg))
    items = [Item(i) for i in range(len(records))]

    # 3. Redact: mask personal-looking data in the copy sent to models.
    with step(ctx, "redact") as s:
        for it, rec in zip(items, records):
            it.text, it.pii = redact(note_text(rec.get("notes")))
            if not it.text:
                it.status, it.reason = "no_notes", "notes field empty: no model call"
        with_text = [it for it in items if it.text]
        s.rows_in, s.rows_out = len(items), len(with_text)
        s.message = (f"{sum(it.pii for it in items)} personal-data patterns masked; "
                     f"{len(items) - len(with_text)} records have no notes")

    # 4. Route: show where classification will go and why.
    with step(ctx, "route") as s:
        plan = Counter(route("classify", {"text": it.text}, gw.context()) for it in with_text)
        s.rows_in = s.rows_out = len(with_text)
        s.message = "; ".join(f"classify -> {r.expert} x{n} ({r.reason})" for r, n in plan.items()) or "nothing to route"

    # 5a. Classify: category, urgency, injection.
    eligible: list[Item] = []
    with step(ctx, "classify") as s:
        threshold = mcfg["category_confidence_threshold"]
        for it in with_text:
            it.classification, it.classify_expert = _classify(gw, it, questions, qver)
            inj = it.classification["injection"]["probs"]["true"]
            conf = it.classification["category"]["confidence"]
            if inj >= mcfg["injection_threshold"]:
                it.status = "quarantined"
                it.reason = f"injection probability {inj:.2f} ({it.classify_expert}): not acted on"
                open_incident(ctx, "injection",
                              f"{ctx.file_name} row {it.row_index}: note tries to give instructions "
                              f"(p={inj:.2f}, {it.classify_expert}); record quarantined, text treated as data")
            elif conf < threshold:
                it.status, it.reason = "review", f"category confidence {conf:.2f} < {threshold}"
                run_sql(ctx, "classify",
                        "INSERT INTO review_queue (review_id, run_id, file_name, row_index, reason, status, opened_at) "
                        "VALUES (?, ?, ?, ?, ?, 'open', ?)",
                        (f"rev-{uuid.uuid4().hex[:8]}", ctx.run_id, ctx.file_name, it.row_index, it.reason, now_iso()))
            else:
                eligible.append(it)
        experts_used = Counter(it.classify_expert for it in with_text)
        s.rows_in, s.rows_out = len(with_text), len(eligible)
        s.rows_rejected = len(with_text) - len(eligible)
        s.status = "warning" if s.rows_rejected else "ok"
        s.message = (f"by {dict(experts_used)}; "
                     f"{sum(it.status == 'quarantined' for it in with_text)} quarantined (injection), "
                     f"{sum(it.status == 'review' for it in with_text)} to review queue")

    # 5b. Extract: Haiku pulls values from the note.
    with step(ctx, "extract") as s:
        for it in eligible:
            r = route("extract", {"text": it.text}, gw.context())
            if r.reason.startswith("token budget"):
                gw.note_budget_reached()
            try:
                res, parsed = gw.call("extract", "extract", r.expert, pver, it.text,
                                      lambda e: e.extract(it.text, template), _validate_extraction)
                it.extraction, it.extract_expert = parsed.model_dump(), r.expert
                needs_more = r.expert == "haiku" and parsed.confidence == "low"
                if needs_more:
                    it.escalate_reason = "Haiku confidence low"
                gw.log("extract", "extract", r.expert, r.reason, pver, result=res,
                       confidence=1.0 if parsed.confidence == "high" else 0.0,
                       outcome="escalated" if needs_more else "valid", pii=it.pii, row_index=it.row_index)
            except InvalidAnswer as exc:
                gw.log("extract", "extract", r.expert, f"{r.reason}; invalid: {short(exc.error)}", pver,
                       result=exc.result, outcome="escalated", pii=it.pii, row_index=it.row_index)
                it.escalate_reason = f"{r.expert} answer failed validation"
            except Exception as exc:
                gw.log("extract", "extract", r.expert, f"{r.reason}; failed: {short(exc)}", pver,
                       outcome="failed", pii=it.pii, row_index=it.row_index)
                res, parsed = gw.call("extract", "extract", "rules", pver, it.text,
                                      lambda e: e.extract(it.text), _validate_extraction)
                it.extraction, it.extract_expert = parsed.model_dump(), "rules"
                gw.log("extract", "extract", "rules", f"fallback: {r.expert} failed", pver, result=res,
                       confidence=0.0, outcome="valid", pii=it.pii, row_index=it.row_index)
        s.rows_in = len(eligible)
        s.rows_out = sum(it.extraction is not None for it in eligible)
        s.message = (f"by {dict(Counter(it.extract_expert for it in eligible if it.extract_expert))}; "
                     f"{sum(bool(it.escalate_reason) for it in eligible)} need escalation")

    # 6. Validate: escalate to Sonnet once; still invalid -> quarantine. Then record each outcome.
    with step(ctx, "validate") as s:
        for it in eligible:
            if not it.escalate_reason:
                it.status = "extracted"
                it.reason = ("rules fallback: values not checked by a model" if it.extract_expert == "rules"
                             else "valid")
                continue
            r = route("extract", {"text": it.text}, gw.context(escalate=it.escalate_reason))
            if r.expert != "sonnet":
                it.status = "review" if it.extraction else "quarantined"
                it.reason = f"needed escalation but {r.reason}"
                continue
            try:
                res, parsed = gw.call("validate", "escalate", "sonnet", pver, it.text,
                                      lambda e: e.extract(it.text, template), _validate_extraction)
                it.extraction, it.extract_expert = parsed.model_dump(), "sonnet"
                low = parsed.confidence == "low"
                it.status = "review" if low else "extracted"
                it.reason = "low confidence after escalation" if low else f"valid after escalation ({it.escalate_reason})"
                gw.log("validate", "escalate", "sonnet", r.reason, pver, result=res,
                       confidence=0.0 if low else 1.0, outcome="valid", pii=it.pii, row_index=it.row_index)
            except InvalidAnswer as exc:
                gw.log("validate", "escalate", "sonnet", f"{r.reason}; invalid: {short(exc.error)}", pver,
                       result=exc.result, outcome="quarantined", pii=it.pii, row_index=it.row_index)
                it.status, it.reason = "quarantined", "invalid after escalation"
                it.extraction = None
                open_incident(ctx, "failure", f"{ctx.file_name} row {it.row_index}: extraction invalid after "
                                              f"escalation to Sonnet; record quarantined")
            except Exception as exc:
                gw.log("validate", "escalate", "sonnet", f"{r.reason}; failed: {short(exc)}", pver,
                       outcome="failed", pii=it.pii, row_index=it.row_index)
                it.status = "review" if it.extraction else "quarantined"
                it.reason = "escalation failed"
            if it.status == "review":
                run_sql(ctx, "validate",
                        "INSERT INTO review_queue (review_id, run_id, file_name, row_index, reason, status, opened_at) "
                        "VALUES (?, ?, ?, ?, ?, 'open', ?)",
                        (f"rev-{uuid.uuid4().hex[:8]}", ctx.run_id, ctx.file_name, it.row_index, it.reason, now_iso()))

        for it in items:
            c = it.classification
            run_sql(ctx, "validate",
                    "INSERT OR REPLACE INTO record_status (file_name, row_index, run_id, has_notes, pii_redacted, "
                    "category, category_confidence, urgency, injection_probability, classify_expert, extract_expert, "
                    "extraction_json, status, reason, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (ctx.file_name, it.row_index, ctx.run_id, int(bool(it.text)), it.pii,
                     c["category"]["choice"] if c else None, round(c["category"]["confidence"], 4) if c else None,
                     c["urgency"]["choice"] if c else None, round(c["injection"]["probs"]["true"], 4) if c else None,
                     it.classify_expert or None, it.extract_expert or None,
                     json.dumps(it.extraction) if it.extraction else None, it.status, it.reason, now_iso()))

        counts = Counter(it.status for it in items)
        s.rows_in = len(items)
        s.rows_out = counts.get("extracted", 0) + counts.get("no_notes", 0)
        s.rows_rejected = counts.get("quarantined", 0) + counts.get("review", 0)
        s.status = "warning" if s.rows_rejected else "ok"
        s.message = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    return dict(counts)
