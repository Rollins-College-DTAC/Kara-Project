"""Models (MoE) page (references/dashboard.md, references/models-moe.md): which expert
handled what and when -- swimlane timeline, task-to-expert flow, per-expert table.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.db import all_model_usage, read_only_connection, sqlite_path
from dashboard.models import per_expert_summary, task_expert_counts

st.set_page_config(page_title="Law School Outcomes Agent — Models (MoE)", layout="wide")
st.title("Models (MoE)")
st.caption("Simulated data only. Portfolio demonstration, not a real law-school comparison tool.")
st.caption("\"Mixture of experts\" here is an application-level router sending each task to an "
          "expert model, not the learned-gate architecture inside some large models.")

PATH = sqlite_path()
if not PATH.exists():
    st.info("No data yet. Run the generator and the agent loop, then reload this page.")
    st.stop()

conn = read_only_connection(PATH)
usage = all_model_usage(conn)
conn.close()

if not usage:
    st.info("No model calls logged yet.")
    st.stop()

st.subheader("Swimlane: calls over time, one lane per expert")
swim = [{"called_at": datetime.fromisoformat(r["called_at"]), "expert": r["expert"], "task": r["task"]}
        for r in usage]
st.scatter_chart(swim, x="called_at", y="expert", color="task")

st.subheader("Task → expert flow")
st.bar_chart(task_expert_counts(usage), x="task", y="count", color="expert")

st.subheader("Per-expert summary")
st.dataframe(per_expert_summary(usage), hide_index=True)

st.subheader("Recent calls")
st.dataframe(usage[:200], hide_index=True)
