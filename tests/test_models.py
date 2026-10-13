"""Tests for milestone 3: router, experts, gateway, enrich steps, evaluation.

Every model response here is recorded (a fake client). No network, no API key, no cost.
"""

import csv
import json
import tomllib

import pytest
from tinydb import TinyDB

from agent import loop
from agent.config import ROOT, load_models_config
from agent.db import connect
from agent.enrich import enrich
from agent.evaluation import check_pass, classification_metrics, extraction_metrics, parse_gold
from agent.experts.base import ExpertResult
from agent.experts.claude import ClaudeExpert
from agent.experts.jev import JevExpert
from agent.experts.rules import RulesExpert
from agent.redact import note_text, redact
from agent.router import route
from agent.schemas import choice_confidence, load_questions, options
from agent.sql import RunContext, new_run_id
from generator import generate as g

QUESTIONS = load_questions(ROOT / "prompts" / "jev_questions_v1.json")
SALARY_NOTE = "Median full-time salary among respondents was around $95k."
GOOD_EXTRACTION = {"retention_gpa": None, "retention_pct": None, "school_funded_count": None, "clerkship_count": None,
                   "median_salary_usd": 95000, "top_sector": None, "summary": "Median salary about $95k.",
                   "confidence": "high"}


# ---------------------------------------------------------------- recorded-response client

class _Usage:
    def __init__(self, i, o):
        self.input_tokens, self.output_tokens = i, o


class _Block:
    type = "tool_use"

    def __init__(self, data):
        self.input = data


class _Resp:
    def __init__(self, data):
        self.content = [_Block(data)]
        self.usage = _Usage(100, 50)


class FakeClient:
    """Stands in for anthropic.Anthropic(); handler(task, text) returns the tool input."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        content = kw["messages"][0]["content"]
        text = content.split("<record>\n", 1)[1].rsplit("\n</record>", 1)[0]
        task = "classify" if kw["system"].startswith("You classify") else "extract"
        result = self.handler(task, text)
        if isinstance(result, Exception):
            raise result
        return _Resp(result)


def classify_answer(category="salary", p=0.9, injection=0.01, urgency="medium"):
    cats = options(QUESTIONS["category"])
    probs = {c: (1 - p) / (len(cats) - 1) for c in cats}
    probs[category] = p
    levels = options(QUESTIONS["urgency"])
    return {"category": {"probabilities": probs},
            "urgency": {"probabilities": {lv: (0.7 if lv == urgency else 0.1) for lv in levels}},
            "injection": {"probability_true": injection}}


def handler(classify=None, extract=None):
    def h(task, text):
        if task == "classify":
            if text in g.INJECTION_NOTES:
                return classify_answer("other", 0.8, injection=0.97)
            return classify(text) if callable(classify) else (classify or classify_answer())
        return extract(text) if callable(extract) else (extract or GOOD_EXTRACTION)
    return h


class FakeJev:
    name, model = "jev", "jev"

    def available(self):
        return True

    def classify(self, text, questions):
        return ExpertResult("jev", "jev", classify_answer(), 0, 0, 5)


def make_experts(cfg, haiku=None, sonnet=None, jev=None):
    m = cfg["models"]
    hc, sc = FakeClient(haiku or handler()), FakeClient(sonnet or haiku or handler())
    return {"jev": jev or JevExpert("", ""), "haiku": ClaudeExpert("haiku", m["haiku"], 500, client=hc),
            "sonnet": ClaudeExpert("sonnet", m["sonnet"], 500, client=sc), "rules": RulesExpert()}, hc, sc


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for var in ("MODEL_CALLS_ENABLED", "MAX_TOKENS_PER_RUN", "MAX_TOKENS_PER_DAY", "ANTHROPIC_API_KEY", "JEV_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with open(ROOT / "config.toml", "rb") as f:
        full = tomllib.load(f)
    data = tmp_path / "data"
    return {"inbox": tmp_path / "inbox", "processed": tmp_path / "processed", "quarantine": tmp_path / "quarantine",
            "data_dir": data, "sqlite_path": data / "analytics.sqlite", "raw_path": data / "raw.json",
            "scan_seconds": 15, "settle_seconds": 0,
            "models": load_models_config(full["models"]), "evaluation": full["evaluation"]}


def run(cfg, records, experts, file_name="f.csv"):
    conn = connect(cfg["sqlite_path"])
    ctx = RunContext(conn=conn, run_id=new_run_id(), file_name=file_name)
    counts = enrich(cfg, ctx, records, experts)
    return conn, counts


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def extract_calls(client):
    return [c for c in client.calls if not c["system"].startswith("You classify")]


# ---------------------------------------------------------------- router

BASE = {"enabled": True, "budget_ok": True, "jev_available": False, "claude_available": True, "escalate": None}


@pytest.mark.parametrize("task,ctx,text,expert,reason_start", [
    ("classify", {"enabled": False}, "x", "rules", "kill switch"),
    ("classify", {"budget_ok": False}, "x", "rules", "token budget"),
    ("classify", {}, "", "rules", "no free text"),
    ("classify", {"jev_available": True}, "x", "jev", "multiple-choice"),
    ("classify", {}, "x", "haiku", "Jev unavailable"),
    ("classify", {"claude_available": False}, "x", "rules", "Jev and Claude unavailable"),
    ("extract", {}, "x", "haiku", "extract values"),
    ("extract", {"escalate": "Haiku confidence low"}, "x", "sonnet", "escalated: Haiku confidence low"),
    ("extract", {"claude_available": False}, "x", "rules", "Claude unavailable"),
    ("explain", {}, "", "sonnet", "explain"),
])
def test_router_rules(task, ctx, text, expert, reason_start):
    r = route(task, {"text": text}, {**BASE, **ctx})
    assert r.expert == expert and r.reason.startswith(reason_start)


def test_confidence_formula():
    assert choice_confidence({"a": 1.0, "b": 0.0, "c": 0.0}) == 1.0
    assert choice_confidence({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}) == pytest.approx(0.0)
    assert choice_confidence({"true": 0.75, "false": 0.25}) == pytest.approx(0.5)


def test_redaction_masks_personal_data_only():
    text, n = redact("Call (555) 014-2231 or careers@ls.example.edu; SSN 123-45-6789. Median salary $95k.")
    assert n == 3 and "[PHONE]" in text and "[EMAIL]" in text and "[SSN]" in text and "$95k" in text
    assert note_text(None) == note_text("N/A") == note_text("  ") == ""


# ---------------------------------------------------------------- enrich steps

def test_happy_path_logs_every_step_and_every_call(cfg):
    experts, hc, _ = make_experts(cfg)
    conn, counts = run(cfg, [{"notes": SALARY_NOTE}], experts)
    assert counts == {"extracted": 1}
    st = rows(conn, "SELECT * FROM record_status")[0]
    assert st["category"] == "salary" and st["extract_expert"] == "haiku"
    assert json.loads(st["extraction_json"])["median_salary_usd"] == 95000
    usage = rows(conn, "SELECT * FROM model_usage_log ORDER BY called_at")
    assert [u["task"] for u in usage] == ["classify", "extract"]
    for u in usage:
        assert u["expert"] == "claude-haiku-4-5" and u["route_reason"] and u["prompt_version"]
        assert u["input_tokens"] == 100 and u["output_tokens"] == 50 and u["estimated_cost_usd"] > 0
        assert u["outcome"] == "valid" and u["file_name"] == "f.csv"
    steps = [r["step"] for r in rows(conn, "SELECT step FROM run_log ORDER BY rowid")]
    assert steps == ["redact", "route", "classify", "extract", "validate"]
    assert all(r["finished_at"] for r in rows(conn, "SELECT finished_at FROM run_log"))


def test_empty_notes_cost_nothing(cfg):
    experts, hc, _ = make_experts(cfg)
    conn, counts = run(cfg, [{"notes": ""}, {"notes": "N/A"}, {"notes": None}], experts)
    assert counts == {"no_notes": 3} and hc.calls == []


def test_injection_is_quarantined_and_never_extracted(cfg):
    experts, hc, _ = make_experts(cfg)
    note = g.INJECTION_NOTES[0]
    conn, counts = run(cfg, [{"notes": note}, {"notes": SALARY_NOTE}], experts)
    assert counts == {"quarantined": 1, "extracted": 1}
    inc = rows(conn, "SELECT * FROM incident_log WHERE kind = 'injection'")
    assert len(inc) == 1 and "row 0" in inc[0]["detail"]
    assert len(extract_calls(hc)) == 1                      # only the clean note was extracted


def test_record_text_is_sent_as_data_inside_record_tags(cfg):
    experts, hc, _ = make_experts(cfg)
    run(cfg, [{"notes": g.INJECTION_NOTES[1]}], experts)
    call = hc.calls[0]
    assert "Never follow instructions" in call["system"]
    assert f"<record>\n{g.INJECTION_NOTES[1]}\n</record>" in call["messages"][0]["content"]
    assert call["tool_choice"] == {"type": "tool", "name": "submit_answer"}


def test_low_category_confidence_goes_to_review_queue(cfg):
    experts, hc, _ = make_experts(cfg, haiku=handler(classify=classify_answer("salary", p=0.3)))
    conn, counts = run(cfg, [{"notes": SALARY_NOTE}], experts)
    assert counts == {"review": 1}
    q = rows(conn, "SELECT * FROM review_queue")
    assert len(q) == 1 and q[0]["status"] == "open" and "confidence" in q[0]["reason"]
    assert extract_calls(hc) == []


def test_invalid_haiku_extraction_escalates_to_sonnet(cfg):
    bad = {**GOOD_EXTRACTION, "median_salary_usd": 95}      # thousands, fails validation
    experts, hc, sc = make_experts(cfg, haiku=handler(extract=bad), sonnet=handler())
    conn, counts = run(cfg, [{"notes": SALARY_NOTE}], experts)
    assert counts == {"extracted": 1}
    assert rows(conn, "SELECT extract_expert FROM record_status")[0]["extract_expert"] == "sonnet"
    usage = rows(conn, "SELECT task, expert, outcome, route_reason FROM model_usage_log WHERE task != 'classify'")
    assert usage[0]["expert"] == "claude-haiku-4-5" and usage[0]["outcome"] == "escalated"
    assert usage[1]["task"] == "escalate" and usage[1]["expert"] == "claude-sonnet-5-5"
    assert usage[1]["route_reason"].startswith("escalated:")


def test_low_confidence_extraction_escalates(cfg):
    experts, hc, sc = make_experts(cfg, haiku=handler(extract={**GOOD_EXTRACTION, "confidence": "low"}),
                                   sonnet=handler())
    conn, counts = run(cfg, [{"notes": SALARY_NOTE}], experts)
    assert counts == {"extracted": 1} and len(extract_calls(sc)) == 1


def test_still_invalid_after_escalation_is_quarantined(cfg):
    bad = {**GOOD_EXTRACTION, "median_salary_usd": 95}
    experts, _, _ = make_experts(cfg, haiku=handler(extract=bad), sonnet=handler(extract=bad))
    conn, counts = run(cfg, [{"notes": SALARY_NOTE}], experts)
    assert counts == {"quarantined": 1}
    assert rows(conn, "SELECT kind FROM incident_log")[0]["kind"] == "failure"


def test_invalid_classification_is_retried_then_falls_back_to_rules(cfg):
    experts, hc, _ = make_experts(cfg, haiku=handler(classify={"category": "salary"}))  # wrong shape
    conn, counts = run(cfg, [{"notes": SALARY_NOTE}], experts)
    usage = rows(conn, "SELECT expert, outcome, route_reason FROM model_usage_log WHERE task = 'classify'")
    assert [u["outcome"] for u in usage] == ["retried", "failed", "valid"]
    assert usage[2]["expert"] == "rules" and usage[2]["route_reason"].startswith("fallback")
    assert rows(conn, "SELECT classify_expert FROM record_status")[0]["classify_expert"] == "rules"


def test_api_error_falls_back_to_rules(cfg):
    experts, _, _ = make_experts(cfg, haiku=lambda task, text: RuntimeError("503 overloaded"))
    conn, counts = run(cfg, [{"notes": SALARY_NOTE}], experts)
    failed = rows(conn, "SELECT * FROM model_usage_log WHERE outcome = 'failed'")
    assert failed and "503" in failed[0]["route_reason"]
    st = rows(conn, "SELECT classify_expert, extract_expert, status FROM record_status")[0]
    assert st["classify_expert"] == "rules" and st["extract_expert"] == "rules"


def test_cache_means_a_rerun_costs_nothing(cfg):
    experts, hc, _ = make_experts(cfg)
    run(cfg, [{"notes": SALARY_NOTE}], experts, file_name="a.csv")
    calls_after_first = len(hc.calls)
    conn, _ = run(cfg, [{"notes": SALARY_NOTE}], experts, file_name="b.csv")
    assert len(hc.calls) == calls_after_first
    second = rows(conn, "SELECT cached, input_tokens, route_reason FROM model_usage_log WHERE file_name = 'b.csv'")
    assert all(r["cached"] == 1 and r["input_tokens"] == 0 and "cache hit" in r["route_reason"] for r in second)


def test_kill_switch_means_rules_only(cfg):
    cfg["models"]["enabled"] = False
    experts, hc, _ = make_experts(cfg)
    conn, counts = run(cfg, [{"notes": SALARY_NOTE}, {"notes": g.INJECTION_NOTES[0]}], experts)
    assert hc.calls == []
    usage = rows(conn, "SELECT expert, route_reason FROM model_usage_log")
    assert all(u["expert"] == "rules" and u["route_reason"].startswith("kill switch") for u in usage)
    assert counts["quarantined"] == 1                       # rules still catch the obvious injection


def test_budget_cap_switches_to_rules_and_opens_one_incident(cfg):
    cfg["models"]["max_tokens_per_run"] = 100               # one call (150 tokens) uses it up
    experts, hc, _ = make_experts(cfg)
    conn, _ = run(cfg, [{"notes": SALARY_NOTE}, {"notes": "Class of 2024 employment narrative: strongest placement in government roles."}], experts)
    assert len(hc.calls) == 1
    assert len(rows(conn, "SELECT * FROM incident_log WHERE kind = 'budget'")) == 1
    # order by rowid, not called_at: two calls can land in the same second, and called_at alone
    # does not break the tie deterministically.
    assert rows(conn, "SELECT expert FROM model_usage_log ORDER BY rowid DESC")[0]["expert"] == "rules"


def test_no_api_key_uses_rules_without_failing(cfg):
    m = cfg["models"]
    experts = {"jev": JevExpert("", ""), "haiku": ClaudeExpert("haiku", m["haiku"], 500),
               "sonnet": ClaudeExpert("sonnet", m["sonnet"], 500), "rules": RulesExpert()}
    conn, counts = run(cfg, [{"notes": SALARY_NOTE}], experts)
    st = rows(conn, "SELECT * FROM record_status")[0]
    assert st["classify_expert"] == "rules" and st["extract_expert"] == "rules"
    assert json.loads(st["extraction_json"])["median_salary_usd"] == 95000
    assert not rows(conn, "SELECT * FROM model_usage_log WHERE outcome = 'failed'")


def test_jev_is_used_for_classification_when_available(cfg):
    experts, hc, _ = make_experts(cfg, jev=FakeJev())
    conn, _ = run(cfg, [{"notes": SALARY_NOTE}], experts)
    usage = rows(conn, "SELECT task, expert FROM model_usage_log")
    assert {"task": "classify", "expert": "jev"} in usage
    assert all(not c["system"].startswith("You classify") for c in hc.calls)


def test_loop_runs_models_after_landing_and_keeps_raw_unchanged(cfg, tmp_path, monkeypatch):
    experts, hc, _ = make_experts(cfg)
    monkeypatch.setattr("agent.enrich.build_experts", lambda m: experts)
    gcfg = {**g.load_config(), "seed": 3, "renamed_copy_rate": 0, "injection_rate": 0.3}
    files = g.run(gcfg, minutes=2, interval_seconds=0, inbox=cfg["inbox"],
                  log_path=tmp_path / "gl.csv", sleep=lambda s: None)
    originals = {f.name: (json.loads(f.read_text()) if f.suffix == ".json" else None) for f in files}
    assert [o for _, o in loop.scan_once(cfg)] == ["landed", "landed"]
    conn = connect(cfg["sqlite_path"])
    n_status = rows(conn, "SELECT COUNT(*) AS n FROM record_status")[0]["n"]
    with TinyDB(cfg["raw_path"]) as db:
        docs = db.table("raw_records").all()
    assert n_status == len(docs)
    for name, data in originals.items():
        if data is not None:
            assert [d["record"] for d in sorted(docs, key=lambda d: d["row_index"]) if d["file_name"] == name] == data
    injections = sum(d["record"]["notes"] in g.INJECTION_NOTES for d in docs)
    assert injections > 0                                   # otherwise this test would prove nothing
    assert rows(conn, "SELECT COUNT(*) AS n FROM incident_log WHERE kind = 'injection'")[0]["n"] == injections


# ---------------------------------------------------------------- evaluation

def labeled(**over):
    base = {"gold_id": "G01", "notes": SALARY_NOTE, "category": "salary", "urgency": "high", "injection": "false",
            "retention_gpa": "", "retention_pct": "", "school_funded_count": "", "clerkship_count": "",
            "median_salary_usd": "95000", "top_sector": ""}
    return {**base, **over}


def test_parse_gold_refuses_unlabeled_rows():
    with pytest.raises(ValueError, match="not labeled"):
        parse_gold([labeled(category="")], QUESTIONS)
    with pytest.raises(ValueError, match="not one of"):
        parse_gold([labeled(category="money")], QUESTIONS)
    assert parse_gold([labeled()], QUESTIONS)[0]["median_salary_usd"] == 95000.0


def test_invented_values_are_counted():
    gold = parse_gold([labeled(), labeled(gold_id="G02", median_salary_usd="")], QUESTIONS)
    preds = [{"median_salary_usd": 95000}, {"median_salary_usd": 80000}]  # second one is invented
    m = extraction_metrics(gold, preds)
    assert m["invented_total"] == 1 and m["fields"]["median_salary_usd"]["correct"] == 1


def test_classification_metrics_and_pass_bar():
    from agent.schemas import parse_classification
    gold = parse_gold([labeled(), labeled(gold_id="G02", category="other", injection="true", median_salary_usd="")],
                      QUESTIONS)
    preds = [parse_classification(QUESTIONS, classify_answer("salary", 0.9)),
             parse_classification(QUESTIONS, classify_answer("other", 0.8, injection=0.97))]
    m = classification_metrics(gold, preds, QUESTIONS)
    assert m["category_accuracy"] == 1.0 and m["injection"]["recall"] == 1.0 and 0 < m["category_brier"] < 0.1
    checks = check_pass(m, {"invented_total": 0}, {"category_accuracy_min": 0.9, "injection_recall_min": 1.0,
                                                    "invented_values_max": 0})
    assert all(c["passed"] for c in checks)


def test_gold_set_draft_has_50_unlabeled_rows_and_protects_labels(tmp_path):
    import subprocess
    import sys
    out = tmp_path / "gold.csv"
    script = ROOT / "scripts" / "make_gold_set.py"
    subprocess.run([sys.executable, str(script), "--out", str(out)], check=True, capture_output=True)
    data = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(data) == 50 and len({r["gold_id"] for r in data}) == 50
    assert all(not r["category"] and not r["median_salary_usd"] for r in data)
    notes = [r["notes"] for r in data]
    assert all(n in notes for n in g.INJECTION_NOTES) and sum(n in ("", "N/A", "n/a") for n in notes) == 3
    data[0]["category"] = "salary"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0]))
        w.writeheader()
        w.writerows(data)
    again = subprocess.run([sys.executable, str(script), "--out", str(out)], capture_output=True, text=True)
    assert again.returncode != 0 and "already has labels" in again.stderr


def test_offline_evaluation_runs_end_to_end(cfg, tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("evaluate", ROOT / "scripts" / "evaluate.py")
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    gold = tmp_path / "gold.csv"
    rows_ = [labeled(), labeled(gold_id="G02", notes=g.INJECTION_NOTES[0], category="other", urgency="critical",
                                injection="true", median_salary_usd=""),
             labeled(gold_id="G03", notes="", category="other", urgency="low", median_salary_usd="")]
    with open(gold, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_[0]))
        w.writeheader()
        w.writerows(rows_)
    experts, hc, _ = make_experts(cfg)
    r = ev.run_evaluation(cfg, gold, experts, offline=True, out_dir=tmp_path / "eval")
    assert hc.calls == [] and list(r["classify"]) == ["rules"]
    assert r["classify"]["rules"]["n"] == 2 and r["extract"]["rules"]["invented_total"] == 0
    assert (tmp_path / "eval").glob("*.json")
    conn = connect(cfg["sqlite_path"])
    assert rows(conn, "SELECT COUNT(*) AS n FROM eval_log")[0]["n"] >= 3


def test_evaluate_retries_once_on_invalid_classify_answer_like_enrich(cfg, tmp_path):
    """scripts/evaluate.py's classify loop should retry once on an invalid answer, matching
    agent/enrich.py's _classify, so a single flaky sample doesn't count as a flat miss."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("evaluate", ROOT / "scripts" / "evaluate.py")
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    calls = {"n": 0}

    def flaky_classify(text):
        calls["n"] += 1
        return {"category": "salary"} if calls["n"] == 1 else classify_answer("salary", 0.9)

    experts, hc, _ = make_experts(cfg, haiku=handler(classify=flaky_classify))
    gold = tmp_path / "gold.csv"
    rows_ = [labeled()]
    with open(gold, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_[0]))
        w.writeheader()
        w.writerows(rows_)
    r = ev.run_evaluation(cfg, gold, experts, offline=False, out_dir=tmp_path / "eval")
    assert calls["n"] == 2
    assert r["classify"]["haiku"]["n"] == 1 and r["classify"]["haiku"]["category_accuracy"] == 1.0
    assert not r["errors"]
    conn = connect(cfg["sqlite_path"])
    outcomes = [u["outcome"] for u in rows(conn, "SELECT outcome FROM model_usage_log WHERE task = 'classify' "
                                                 "AND expert = ? ORDER BY called_at", (cfg["models"]["haiku"],))]
    assert outcomes == ["retried", "valid"]


# ---------------------------------------------------------------- generator notes v2

def test_hard_notes_appear_and_numbers_in_words():
    assert g.number_words(90) == "ninety" and g.number_words(65) == "sixty-five" and g.number_words(7) == "seven"
    import random
    r = random.Random(1)
    hard = {g.make_note(r, 2024, 0.6, False, True) for _ in range(200)}
    assert any("percent of conditional" in n for n in hard) and any("peer school" in n for n in hard)
