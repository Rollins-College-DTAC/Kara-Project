"""Data page (references/dashboard.md): clean records with filters, data-quality metrics,
imports per minute.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.db import (distinct_grad_years, distinct_school_codes, distinct_statuses,
                          imports_per_minute, read_only_connection, silver_records, sqlite_path)
from dashboard.quality import flag_counts, status_breakdown

st.set_page_config(page_title="Law School Outcomes Agent — Data", layout="wide")
st.title("Data")
st.caption("Simulated data only. Portfolio demonstration, not a real law-school comparison tool.")

PATH = sqlite_path()
if not PATH.exists():
    st.info("No data yet. Run the generator and the agent loop, then reload this page.")
    st.stop()

conn = read_only_connection(PATH)

st.subheader("Data quality")
everything = silver_records(conn, limit=100000)
n_total = len(everything)
n_consistent = sum(1 for r in everything if r["consistency_ok"])
n_unknown_school = sum(1 for r in everything if r["school_code"] is None)
by_status = status_breakdown(everything)

cols = st.columns(4)
cols[0].metric("Total records", n_total)
cols[1].metric("Consistent", f"{n_consistent / n_total:.0%}" if n_total else "—")
cols[2].metric("Published", by_status.get("published", 0))
cols[3].metric("Unknown school code", n_unknown_school)

flags = flag_counts(everything)
if flags:
    st.write("Broken consistency rules (a record can break more than one):")
    st.dataframe([{"rule": k, "records": v} for k, v in sorted(flags.items(), key=lambda kv: -kv[1])],
                hide_index=True)

st.subheader("Imports per minute")
ipm = list(reversed(imports_per_minute(conn)))
if ipm:
    st.bar_chart(ipm, x="minute", y="n")
else:
    st.caption("No landed imports yet.")

st.subheader("Records")
f1, f2, f3 = st.columns(3)
status = f1.selectbox("Status", ["(all)"] + distinct_statuses(conn))
school = f2.selectbox("School code", ["(all)"] + distinct_school_codes(conn))
years = [str(y) for y in distinct_grad_years(conn)]
year = f3.selectbox("Grad year", ["(all)"] + years)

filtered = silver_records(
    conn,
    status=None if status == "(all)" else status,
    school_code=None if school == "(all)" else school,
    grad_year=None if year == "(all)" else int(year),
)
st.caption(f"{len(filtered)} record(s) match (showing up to 5000)")
st.dataframe(filtered, hide_index=True)

conn.close()
