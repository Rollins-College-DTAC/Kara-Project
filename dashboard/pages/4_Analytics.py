"""Analytics page (references/dashboard.md): the student's statistical methods, the forecast
and backtest, trigger precision and recall. Each chart has a "How this was calculated" expander.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from agent.config import ROOT
from agent.forecast import SEASONAL_PERIODS, backtest, fit_and_forecast, naive_forecast
from agent.stats import aggregate_by_school
from dashboard.analytics import load_generator_log, trigger_precision_recall
from dashboard.db import (all_decisions, batch_mean_series, latest_stats, read_only_connection,
                          silver_records, sqlite_path)

st.set_page_config(page_title="Law School Outcomes Agent — Analytics", layout="wide")
st.title("Analytics")
st.caption("Simulated data only. Portfolio demonstration, not a real law-school comparison tool.")

PATH = sqlite_path()
if not PATH.exists():
    st.info("No data yet. Run the generator and the agent loop, then reload this page.")
    st.stop()

conn = read_only_connection(PATH)
stats = latest_stats(conn)

if not stats:
    st.info("No statistics yet. Run `uv run python scripts/compute_stats.py`.")
else:
    st.caption(f"From the most recent `scripts/compute_stats.py` run ({stats[0]['computed_at']}).")

    ci_rows = [s for s in stats if s["method"] == "wilson_ci"]
    if ci_rows:
        st.subheader("Employment rate by school: Wilson 95% confidence interval")
        table = []
        for s in ci_rows:
            inputs = json.loads(s["inputs_json"])
            table.append({"school_code": inputs.get("school_code"), "p_hat": s["result"],
                         "ci_low": inputs.get("ci_low"), "ci_high": inputs.get("ci_high"), "n": inputs.get("n")})
        st.dataframe(sorted(table, key=lambda r: r["school_code"] or ""), hide_index=True)
        with st.expander("How this was calculated"):
            st.latex(ci_rows[0]["formula_latex"])
            st.write(ci_rows[0]["interpretation"])

    two_prop = next((s for s in stats if s["method"] == "two_proportion_z_test"), None)
    if two_prop:
        st.subheader("Public vs private: two-proportion z-test")
        st.write(two_prop["interpretation"])
        with st.expander("How this was calculated"):
            st.latex(two_prop["formula_latex"])
            st.json(json.loads(two_prop["inputs_json"]))

    corr = next((s for s in stats if s["method"] == "pearson_correlation_and_regression"), None)
    if corr:
        st.subheader("Median LSAT vs employment rate: correlation and regression")
        st.write(corr["interpretation"])
        rows_for_scatter = silver_records(conn, status="published", limit=100000)
        agg = aggregate_by_school(rows_for_scatter)
        scatter = [{"median_lsat_50": a.median_lsat_50, "emp_rate": a.emp_rate} for a in agg.values() if a.grads]
        if scatter:
            st.scatter_chart(scatter, x="median_lsat_50", y="emp_rate")
        with st.expander("How this was calculated"):
            st.latex(corr["formula_latex"])
            st.json(json.loads(corr["inputs_json"]))

st.subheader("Forecast: employment rate, next imports")
series_rows = batch_mean_series(conn)
values = [r["emp_rate"] for r in series_rows]
min_needed = 2 * SEASONAL_PERIODS
if len(values) < min_needed:
    st.caption(f"Need at least {min_needed} published imports for a seasonal forecast "
              f"(have {len(values)}). Run more imports through the loop to see this.")
else:
    horizon = 6
    try:
        mean, lo, hi = fit_and_forecast(values, horizon)
        naive = naive_forecast(values, horizon)
        chart: dict[int, dict] = {i: {"t": i, "actual": v} for i, v in enumerate(values)}
        chart[len(values) - 1]["forecast"] = values[-1]
        chart[len(values) - 1]["naive"] = values[-1]
        for h in range(horizon):
            t = len(values) + h
            chart[t] = {"t": t, "forecast": mean[h], "naive": naive[h]}
        st.line_chart(list(chart.values()), x="t", y=["actual", "forecast", "naive"])

        st.write(f"Next {horizon} imports, with a 95% prediction interval:")
        st.dataframe([{"imports_ahead": h + 1, "forecast": round(mean[h], 4),
                      "pi_low": round(lo[h], 4), "pi_high": round(hi[h], 4),
                      "naive_baseline": round(naive[h], 4)} for h in range(horizon)], hide_index=True)

        holdout = min(SEASONAL_PERIODS, len(values) // 3)
        bt = backtest(values, holdout)
        st.write(f"Backtest: the last {holdout} published imports held out, scored against what "
                f"actually happened.")
        cols = st.columns(4)
        cols[0].metric("Model MAE", round(bt.model_mae, 4))
        cols[1].metric("Naive MAE", round(bt.naive_mae, 4))
        cols[2].metric("Model MAPE", f"{bt.model_mape:.1f}%" if bt.model_mape is not None else "—")
        cols[3].metric("Naive MAPE", f"{bt.naive_mape:.1f}%" if bt.naive_mape is not None else "—")
        if bt.model_mae >= bt.naive_mae:
            st.warning("The model isn't beating the naive baseline on this backtest.")
        with st.expander("How this was calculated"):
            st.write("ETS model (trend + a 12-import seasonal cycle, matching the generator's own "
                    "batch_target_rate design) vs. a naive 'same as last period' baseline. "
                    "MAE/MAPE computed on the held-out points.")
    except Exception as exc:
        st.warning(f"Forecast failed to fit: {exc}")

st.subheader("Anomaly trigger: precision and recall")
decisions = all_decisions(conn)
generator_rows = load_generator_log(ROOT / "generator_log.csv")
if not decisions:
    st.caption("No decisions logged yet.")
elif not generator_rows:
    st.caption("generator_log.csv not found (it's gitignored and local-only) -- "
              "regenerate the demo data to see this scored against the answer key.")
else:
    pr = trigger_precision_recall(decisions, generator_rows)
    cols = st.columns(4)
    cols[0].metric("Precision", f"{pr['precision']:.0%}" if pr["precision"] is not None else "—")
    cols[1].metric("Recall", f"{pr['recall']:.0%}" if pr["recall"] is not None else "—")
    cols[2].metric("True positives", pr["tp"])
    cols[3].metric("False positives", pr["fp"])
    with st.expander("How this was calculated"):
        st.write("Ground truth: a file whose generator_log.csv row has expected_detector == "
                "'zscore' (a seeded rate_spike or rate_drop) counts as a real anomaly; "
                "everything else (including consistency-check anomalies, which are a different "
                "detector's job) counts as a true negative for this trigger.")
        st.json(pr)

conn.close()
