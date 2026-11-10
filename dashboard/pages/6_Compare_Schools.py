"""Compare Schools page: pick schools and see their employment outcomes and an estimated
value index side by side. Uses only published, consistent records -- the same gold view the
rest of the dashboard reads.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.compare import build_school_profiles
from dashboard.db import read_only_connection, silver_records
from dashboard.resolve import resolve_db_path

st.set_page_config(page_title="Law School Outcomes Agent — Compare Schools", layout="wide")
st.title("Compare Schools")
st.caption("Simulated data only. Portfolio demonstration, not a real law-school comparison tool.")
st.caption("\"Value\" here is an estimated employment rate per $10,000 of invented net cost "
          "(cost of attendance × (1 − scholarship share)). It's illustrative, not a real "
          "net-price or ROI calculation — there's no real salary or debt data behind it.")

PATH = resolve_db_path()
if not PATH.exists():
    st.info("No data yet. Run the generator and the agent loop, then reload this page.")
    st.stop()

conn = read_only_connection(PATH)
rows = silver_records(conn, status="published", limit=100000)
conn.close()

profiles = build_school_profiles(rows)
if not profiles:
    st.info("No published records yet.")
    st.stop()

options = sorted(profiles, key=lambda c: profiles[c].name or c)
labels = {c: f"{profiles[c].name or c} ({c})" for c in options}
chosen = st.multiselect("Schools to compare", options, default=options[:min(3, len(options))],
                        format_func=lambda c: labels[c])

if not chosen:
    st.caption("Pick at least one school above.")
else:
    table = [{
        "School": profiles[c].name or c, "Code": profiles[c].code, "Records": profiles[c].n,
        "Employment rate": profiles[c].emp_rate, "Bar passage rate": profiles[c].bar_pass_rate,
        "Median LSAT": profiles[c].lsat_50, "Median GPA": profiles[c].gpa_50,
        "Scholarship share": profiles[c].scholarship_share,
        "Cost of attendance": profiles[c].cost_of_attendance,
        "Est. net cost": profiles[c].est_net_cost, "Value index": profiles[c].value_index,
    } for c in chosen]
    st.dataframe(table, hide_index=True)

    st.subheader("Employment rate vs. estimated net cost")
    scatter = [{"est_net_cost": profiles[c].est_net_cost, "emp_rate": profiles[c].emp_rate,
               "school": profiles[c].name or c} for c in chosen
              if profiles[c].est_net_cost is not None and profiles[c].emp_rate is not None]
    if scatter:
        st.scatter_chart(scatter, x="est_net_cost", y="emp_rate")
    else:
        st.caption("Not enough cost/outcome data among the selected schools for a chart.")

    with st.expander("How \"value\" is calculated"):
        st.latex(r"\text{est. net cost} = \text{cost of attendance} \times (1 - \text{scholarship share})")
        st.latex(r"\text{value index} = \frac{\text{employment rate}}{\text{est. net cost} / 10{,}000}")
        st.write("A rough, illustrative measure only: cost_of_attendance is an invented sticker "
                "price, and scholarship_share is the *share of the class* with merit aid, not "
                "each student's actual discount. There is no real salary, debt or ROI data "
                "behind this number.")
