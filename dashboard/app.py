"""Live Run page (references/dashboard.md): the live flow chart, a panel per step, the
latest decision, and an alert banner with Release/Reject buttons for every held import.

Run: streamlit run dashboard/app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from agent.release import reject_import, release_import
from dashboard.db import (decision_for, latest_run, model_usage_for, open_trigger_holds,
                          read_only_connection, run_log_for, sql_log_for, writable_connection)
from dashboard.flow import build_dot
from dashboard.remote import trigger_review_workflow
from dashboard.resolve import cloud_review_secrets, resolve_db_path, reviewer_passcode

st.set_page_config(page_title="Law School Outcomes Agent — Live Run", layout="wide")
st.title("Live Run")
st.caption("Simulated data only. Portfolio demonstration, not a real law-school comparison tool.")

PATH = resolve_db_path()
if not PATH.exists():
    st.info("No data yet. Run the generator and the agent loop, then reload this page.")
    st.stop()


def _decide(h: dict, decision: str, reviewer: str, cloud_review: dict | None) -> None:
    """Locally: writes the decision straight to SQLite (agent/release.py). In the cloud
    (cloud_review set): starts review.yml instead -- the dashboard never writes the database
    file directly there (references/dashboard.md)."""
    if cloud_review:
        trigger_review_workflow(cloud_review["owner"], cloud_review["repo"], cloud_review["token"],
                                h["incident_id"], decision, reviewer)
        st.success(f"Requested: the review workflow will {decision} {h['file_name']} shortly.")
    else:
        wconn = writable_connection(PATH)
        apply_decision = release_import if decision == "release" else reject_import
        n = apply_decision(wconn, h["file_name"], reviewer)
        wconn.close()
        if decision == "release":
            st.success(f"Released: {n} rows published.")
        else:
            st.warning(f"Rejected: {n} rows excluded from the gold view.")
    st.rerun()


@st.fragment(run_every=5)
def alert_banner():
    conn = read_only_connection(PATH)
    held = open_trigger_holds(conn)
    conn.close()
    if not held:
        return
    st.warning(f"{len(held)} import(s) held by the anomaly trigger, waiting for release.")

    # Protect the buttons (references/dashboard.md): a public cloud app means anyone can open
    # it, so everyone can see what's held, but only a reviewer who knows the passcode can decide.
    passcode = reviewer_passcode()
    unlocked = True
    if passcode:
        entered = st.text_input("Reviewer passcode", type="password", key="reviewer_passcode_input")
        unlocked = entered == passcode
        if not unlocked:
            st.caption("Enter the reviewer passcode to release or reject a held import.")

    cloud_review = cloud_review_secrets()
    for h in held:
        with st.expander(f"⚠️ {h['file_name']} — {h['n_held']} records held"):
            st.write(h["detail"])
            if not unlocked:
                continue
            name = st.text_input("Your initials (required to decide)", key=f"name-{h['incident_id']}")
            c1, c2 = st.columns(2)
            if c1.button("Release", key=f"release-{h['incident_id']}", disabled=not name.strip()):
                _decide(h, "release", name.strip(), cloud_review)
            if c2.button("Reject", key=f"reject-{h['incident_id']}", disabled=not name.strip()):
                _decide(h, "reject", name.strip(), cloud_review)


alert_banner()


@st.fragment(run_every=5)
def flow_and_panels():
    conn = read_only_connection(PATH)
    run = latest_run(conn)
    if not run:
        st.info("No runs logged yet.")
        conn.close()
        return

    st.subheader(f"Latest run: {run['file_name']}")
    log_rows = run_log_for(conn, run["run_id"])
    decision = decision_for(conn, run["run_id"])
    st.graphviz_chart(build_dot(log_rows, decision))

    sql_rows = sql_log_for(conn, run["run_id"])
    usage_rows = model_usage_for(conn, run["run_id"])
    sql_by_step: dict[str, list[dict]] = {}
    for r in sql_rows:
        sql_by_step.setdefault(r["step"], []).append(r)

    for row in log_rows:
        with st.expander(f"{row['step']} — {row['status']}"):
            st.write(row["message"] or "(no message)")
            cols = st.columns(3)
            cols[0].metric("Rows in", row["rows_in"])
            cols[1].metric("Rows out", row["rows_out"])
            cols[2].metric("Rows rejected", row["rows_rejected"])
            if row["step"] in ("classify", "extract"):
                used = [u for u in usage_rows if u["task"] == row["step"]]
                if used:
                    st.write(f"{len(used)} model call(s) for this step:")
                    st.dataframe([{"expert": u["expert"], "outcome": u["outcome"], "confidence": u["confidence"],
                                  "tokens": u["input_tokens"] + u["output_tokens"], "cost_usd": u["estimated_cost_usd"]}
                                 for u in used], hide_index=True)
            for sql_row in sql_by_step.get(row["step"], []):
                st.code(sql_row["sql_text"], language="sql")
                params = json.loads(sql_row["params_json"]) if sql_row["params_json"] else []
                if params:
                    st.caption(f"params: {params}")

    if decision:
        st.subheader("Decide")
        st.latex(r"z = \frac{\bar x - \mu}{\sigma}")
        st.write(f"statistic (z) = {decision['statistic']}, threshold = {decision['threshold']}, "
                f"fired = {bool(decision['fired'])}")
        st.caption(decision.get("detail") or "")

    conn.close()


flow_and_panels()
