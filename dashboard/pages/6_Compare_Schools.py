"""Compare Schools: a decision view for weighing schools side by side -- outcomes, estimated
cost, and (sample) application status and deadlines. Outcomes come from published, consistent
pipeline records; application status, offers and deadlines are invented sample data
(dashboard/applications.py), clearly labeled as such.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.applications import sample_application, upcoming_deadlines
from dashboard.compare import (admission_odds, build_real_profiles, build_school_profiles, national_trend,
                               rank_by_lsat)
from dashboard.db import (aba_employment, flagged_profiles, read_only_connection, school_profiles,
                          silver_records)
from dashboard.resolve import resolve_db_path
from dashboard.charts import employment_trend_chart, short_name, value_bubble_chart
from dashboard.theme import inject
from dashboard.ui import hero, money, school_card, stat_card, timeline

st.set_page_config(page_title="Compare Schools", layout="wide")
inject()
PATH = resolve_db_path()
if not PATH.exists():
    st.info("No data yet. Run the generator and the agent loop, then reload this page.")
    st.stop()

conn = read_only_connection(PATH)
real_profile_rows = school_profiles(conn)
real_employment = aba_employment(conn)
flagged = flagged_profiles(conn)
rows = [] if real_profile_rows and real_employment else silver_records(conn, status="published", limit=100000)
conn.close()

REAL = bool(real_profile_rows and real_employment)
if REAL:
    profiles = build_real_profiles(real_profile_rows, real_employment)
    st.markdown(hero("Compare Schools", "Real outcomes from the ABA's published disclosures: employment, tuition, "
                     "admissions and bar passage for every ABA-approved law school. Application status and "
                     "deadlines below are invented samples.", []), unsafe_allow_html=True)
else:
    profiles = build_school_profiles(rows)
    st.markdown(hero("Compare Schools", "Outcomes, cost and deadlines side by side. Simulated data only: a portfolio "
                     "demonstration, not a tool for choosing a real law school. Application status, offers, "
                     "deadlines and ranks are invented samples.", []), unsafe_allow_html=True)
if not profiles:
    st.info("No published records yet.")
    st.stop()

ranks = rank_by_lsat(profiles)
today = date.today()

c1, c2, c3 = st.columns([2, 1, 1])
options = sorted(profiles, key=lambda c: profiles[c].name or c)
labels = {c: profiles[c].name or c for c in options}
if REAL:  # start from the schools with the highest median LSAT so the first view is a real comparison
    default = sorted((c for c in options if profiles[c].lsat_50 is not None),
                     key=lambda c: -profiles[c].lsat_50)[:6]
else:
    default = options[:min(6, len(options))]
chosen = c1.multiselect("Schools tracked", options, default=default, format_func=lambda c: labels[c])
my_lsat = c2.number_input("Your LSAT", 120, 180, 165)
my_gpa = c3.number_input("Your GPA", 0.0, 4.33, 3.70, step=0.05)

if not chosen:
    st.caption("Pick at least one school above.")
    st.stop()

apps = {c: sample_application(c, profiles[c].cost_of_attendance, today) for c in chosen}


def net_after_offer(code: str) -> float | None:
    if REAL:  # real estimated net tuition: tuition + fees less the median grant, weighted by who gets one
        return profiles[code].est_net_cost
    cost = profiles[code].cost_of_attendance
    if cost is None:
        return None
    return cost - (apps[code].scholarship_offer or 0)


nets = [n for n in (net_after_offer(c) for c in chosen) if n is not None]
lsats = [profiles[c].lsat_50 for c in chosen if profiles[c].lsat_50 is not None]
events = upcoming_deadlines(list(apps.values()), today)
nxt = events[0] if events else None

overview = (
    stat_card("Schools tracked", str(len(chosen)), "in this comparison", count_to=len(chosen)) +
    stat_card("Average net tuition" if REAL else "Average net cost", money(sum(nets) / len(nets)) if nets else "—",
              "tuition + fees less median grant" if REAL else "after sample scholarship offers") +
    stat_card("Average median LSAT", f"{sum(lsats) / len(lsats):.0f}" if lsats else "—", "across tracked schools") +
    stat_card("Next deadline", nxt[0].strftime("%b %d") if nxt else "—",
              f"{nxt[1]} · {labels[nxt[2]]}" if nxt else "nothing upcoming"))
st.markdown(f'<div class="lsc-grid4">{overview}</div>', unsafe_allow_html=True)

rank_label = "by median LSAT" if REAL else "(sample)"
real_kwargs = lambda c: (dict(  # noqa: E731
    school_type=profiles[c].school_type, trend=profiles[c].trend, employer_shares=profiles[c].employer_shares,
    emp_label=f"classes {profiles[c].years[0]}\u2013{profiles[c].years[1]}" if profiles[c].years else "employed",
    bar_pass=profiles[c].bar_pass_rate, bar_state_avg=profiles[c].bar_state_avg,
    acceptance=profiles[c].acceptance_rate) if REAL else {})
cards = "".join(school_card(
    name=labels[c], code=("" if REAL else c), rank=ranks.get(c), rank_label=rank_label,
    status=None if REAL else apps[c].status, **real_kwargs(c),
    odds=admission_odds(my_lsat, my_gpa, profiles[c].lsat_50, profiles[c].gpa_50),
    lsat=profiles[c].lsat_50, gpa=profiles[c].gpa_50, cost=profiles[c].cost_of_attendance,
    offer=None if REAL else apps[c].scholarship_offer, net=net_after_offer(c), emp_rate=profiles[c].emp_rate,
    breakdown=profiles[c].emp_breakdown) for c in chosen)
st.markdown(f'<div class="lsc-grid2">{cards}</div>', unsafe_allow_html=True)

if REAL:
    st.markdown('<h2 class="lsc-h2">Employment trend by graduating class</h2>', unsafe_allow_html=True)
    series = {"All schools": national_trend(real_employment)}
    series.update({short_name(labels[c]): profiles[c].trend or [] for c in chosen[:8]})
    trend_chart = employment_trend_chart(series)
    if trend_chart is not None:
        st.altair_chart(trend_chart, use_container_width=True, theme=None)
        st.caption("Share of each graduating class employed in a full-time, long-term job that requires bar "
                   "passage, 10 months after graduation. Dashed grey is all ABA schools pooled.")

st.markdown('<h2 class="lsc-h2">Employment rate vs. estimated net cost</h2>', unsafe_allow_html=True)
chart = value_bubble_chart([{
    "school": labels[c], "code": c, "net_cost": profiles[c].est_net_cost, "emp_rate": profiles[c].emp_rate,
    "class_size": profiles[c].class_size, "value_index": profiles[c].value_index, "rank": ranks.get(c)}
    for c in chosen])
if chart is not None:
    st.altair_chart(chart, use_container_width=True, theme=None)
    st.caption("Hover a bubble for details; scroll to zoom and drag to pan. Bubble size is class size, darker "
               "is better value. Dashed lines are the group averages; the top-left is the sweet spot.")
else:
    st.caption("Not enough cost/outcome data among the selected schools for a chart.")

st.markdown('<h2 class="lsc-h2">Upcoming deadlines (sample)</h2>', unsafe_allow_html=True)
st.markdown(timeline([(d, label, labels[code]) for d, label, code in events], today), unsafe_allow_html=True)
st.markdown('<div class="lsc-note">Red: within 14 days. Amber: within 30. Green: later. Sample dates, '
            'regenerated relative to today.</div>', unsafe_allow_html=True)

with st.expander("Full numbers"):
    st.dataframe([{
        "School": labels[c], "Type": profiles[c].school_type, "Records": profiles[c].n, "Employment rate": profiles[c].emp_rate,
        "Bar passage rate": profiles[c].bar_pass_rate, "Median LSAT": profiles[c].lsat_50,
        "Median GPA": profiles[c].gpa_50, "Cost of attendance": profiles[c].cost_of_attendance,
        "Est. net cost (scholarship share)": profiles[c].est_net_cost, "Value index": profiles[c].value_index,
    } for c in chosen], hide_index=True)

if REAL:
    yrs = sorted({r["grad_year"] for r in real_employment})
    st.caption(f"Source: ABA Standard 509 Information Reports and Employment Summary Reports, graduating "
               f"classes {yrs[0]}\u2013{yrs[-1]}; bar passage from the ABA's bar passage data. Employment is "
               "pooled over each school's latest three classes. The ABA assumes no responsibility for "
               "inaccuracies in data schools report.")
    if flagged:
        st.caption("Left out because their reports failed a consistency check: " +
                   ", ".join(sorted(f["school_name"] for f in flagged)) + ".")

with st.expander("How these numbers are calculated"):
    if REAL:
        st.latex(r"\text{est. net tuition} = \text{tuition} + \text{fees} - \text{share receiving grants} "
                 r"\times \text{median grant}")
        st.latex(r"\text{value index} = \frac{\text{employment rate}}{\text{est. net tuition} / 10{,}000}")
        st.write("Employment rate is graduates in full-time, long-term jobs that require bar passage divided by "
                 "all graduates, pooled over three classes so small schools are not whipsawed by one year. "
                 "Net tuition excludes living costs and is an estimate, not what any student pays. Reach/Target/"
                 "Safe compares your LSAT and GPA with a school's medians and is not an admissions model. "
                 "Rank is by median LSAT, not a published ranking.")
    st.latex(r"\text{est. net cost} = \text{cost of attendance} \times (1 - \text{scholarship share})")
    st.latex(r"\text{value index} = \frac{\text{employment rate}}{\text{est. net cost} / 10{,}000}")
    st.write("Illustrative only. Cost is an invented sticker price; scholarship share is the share of the "
             "class with merit aid, not each student's discount. Reach/Target/Safe compares your LSAT and "
             "GPA with a school's medians and is not an admissions model. Employment types are the four "
             "categories the pipeline records (bar-passage-required, JD-advantage, other, unemployed).")
