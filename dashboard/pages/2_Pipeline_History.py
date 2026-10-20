"""Pipeline history page (references/dashboard.md): step durations over the last 30 runs,
rows in/out per run, the log rows for any selected run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.db import (read_only_connection, recent_run_ids, run_log_for, run_log_rows_for_runs,
                          sql_log_for, sqlite_path)
from dashboard.pipeline import rows_per_run, step_duration_summary

st.set_page_config(page_title="Law School Outcomes Agent — Pipeline History", layout="wide")
st.title("Pipeline History")
st.caption("Simulated data only. Portfolio demonstration, not a real law-school comparison tool.")

PATH = sqlite_path()
if not PATH.exists():
    st.info("No data yet. Run the generator and the agent loop, then reload this page.")
    st.stop()

conn = read_only_connection(PATH)
runs = recent_run_ids(conn, limit=30)
if not runs:
    st.info("No runs logged yet.")
    st.stop()

run_ids = [r["run_id"] for r in runs]
all_rows = run_log_rows_for_runs(conn, run_ids)

st.subheader(f"Step durations over the last {len(run_ids)} runs")
st.dataframe(step_duration_summary(all_rows), hide_index=True)

st.subheader("Rows in/out per run (Land step)")
st.dataframe(rows_per_run(all_rows), hide_index=True)

st.subheader("Log for one run")
file_by_run = {r["run_id"]: r["file_name"] for r in runs}
chosen = st.selectbox("Run", run_ids, format_func=lambda rid: file_by_run[rid])

st.write("run_log:")
st.dataframe(run_log_for(conn, chosen), hide_index=True)

st.write("sql_log:")
for r in sql_log_for(conn, chosen):
    st.code(r["sql_text"], language="sql")
    if r["params_json"]:
        st.caption(f"params: {json.loads(r['params_json'])}")

conn.close()
