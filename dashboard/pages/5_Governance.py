"""Governance page (references/dashboard.md, references/governance.md): gold-set scores per
expert, Jev calibration chart, cost against the budget, review queue, incidents, kill-switch
status, links to the docs.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from agent.config import ROOT, load_agent_config
from dashboard.db import (all_eval_log, all_incidents, all_model_usage, all_review_queue,
                          read_only_connection, sqlite_path)
from dashboard.governance import incident_summary, latest_gold_scores, review_queue_summary, tokens_and_cost_on

st.set_page_config(page_title="Law School Outcomes Agent — Governance", layout="wide")
st.title("Governance")
st.caption("Simulated data only. Portfolio demonstration, not a real law-school comparison tool.")

cfg = load_agent_config()

st.subheader("Kill switch")
if cfg["models"]["enabled"]:
    st.success("Model calls are ON. Every classify/extract call can reach Jev or Claude.")
else:
    st.warning("Model calls are OFF (MODEL_CALLS_ENABLED=false or config.toml [models].enabled=false). "
              "Every record falls back to the rules expert.")

PATH = sqlite_path()
if not PATH.exists():
    st.info("No data yet. Run the generator and the agent loop, then reload this page.")
    st.stop()

conn = read_only_connection(PATH)

st.subheader("Gold-set scores per expert")
eval_rows = all_eval_log(conn)
if eval_rows:
    st.dataframe(latest_gold_scores(eval_rows), hide_index=True)
else:
    st.caption("No evaluation logged yet. Run `uv run python scripts/evaluate.py`.")

st.subheader("Jev calibration")
if not cfg["models"].get("jev_base_url"):
    st.caption("Jev is not wired yet (waiting for TypeSafe's request format) -- the router sends "
              "classification to Haiku instead, with that reason logged in model_usage_log.route_reason. "
              "Showing Haiku's own calibration from the most recent evaluation instead.")
eval_dir = ROOT / "docs" / "eval"
eval_files = sorted(eval_dir.glob("eval-*.json")) if eval_dir.exists() else []
if eval_files:
    latest = json.loads(eval_files[-1].read_text(encoding="utf-8"))
    bins = None
    for expert_name in ("jev", "haiku"):
        preds = latest.get("classify", {}).get(expert_name, {})
        if preds.get("calibration"):
            bins = preds["calibration"]
            st.caption(f"From {eval_files[-1].name}, expert: {expert_name}.")
            break
    if bins:
        chart_rows = [b for b in bins if b["n"]]
        if chart_rows:
            st.scatter_chart(chart_rows, x="mean_probability", y="accuracy", size="n")
            st.caption("A well-calibrated expert sits on the diagonal: predicted confidence "
                      "should match actual accuracy in that bin.")
        st.dataframe(bins, hide_index=True)
    else:
        st.caption("No calibration bins in the latest evaluation file.")
else:
    st.caption("No evaluation file in docs/eval/ yet.")

st.subheader("Cost against budget")
usage = all_model_usage(conn)
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
todays = tokens_and_cost_on(usage, today)
total_tokens = sum((r["input_tokens"] or 0) + (r["output_tokens"] or 0) for r in usage)
total_cost = round(sum(r["estimated_cost_usd"] or 0.0 for r in usage), 4)
cols = st.columns(4)
cols[0].metric("Tokens today", f"{todays['tokens']:,} / {cfg['models']['max_tokens_per_day']:,}")
cols[1].metric("Cost today (USD)", f"${todays['cost_usd']}")
cols[2].metric("Tokens, all time", f"{total_tokens:,}")
cols[3].metric("Cost, all time (USD)", f"${total_cost}")
if todays["tokens"] >= cfg["models"]["max_tokens_per_day"]:
    st.warning("Today's token budget is reached; the router falls back to rules until it resets.")

st.subheader("Review queue")
review_rows = all_review_queue(conn)
st.write(review_queue_summary(review_rows) or "Empty.")
if review_rows:
    st.dataframe(review_rows, hide_index=True)

st.subheader("Incidents")
incident_rows = all_incidents(conn)
st.dataframe(incident_summary(incident_rows), hide_index=True)
with st.expander("Most recent incidents"):
    st.dataframe(incident_rows[:100], hide_index=True)

st.subheader("Governance docs")
docs = {"AI use policy": ROOT / "docs" / "ai-use-policy.md", "System card": ROOT / "docs" / "system-card.md",
       "Risk register": ROOT / "docs" / "risk-register.md"}
for label, path in docs.items():
    st.write(f"{label}: {'written' if path.exists() else 'not written yet (milestone 7)'} "
            f"(`{path.relative_to(ROOT)}`)")

conn.close()
