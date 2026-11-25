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
from dashboard.compare import admission_odds, build_school_profiles, rank_by_lsat
from dashboard.db import read_only_connection, silver_records
from dashboard.resolve import resolve_db_path
from dashboard.charts import value_bubble_chart
from dashboard.theme import inject
from dashboard.ui import hero, money, school_card, stat_card, timeline

st.set_page_config(page_title="Compare Schools", layout="wide")
inject()
st.markdown(hero("Compare Schools", "Outcomes, cost and deadlines side by side. Simulated data only: a portfolio "
                 "demonstration, not a tool for choosing a real law school. Application status, offers, "
                 "deadlines and ranks are invented samples.", []), unsafe_allow_html=True)

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

ranks = rank_by_lsat(profiles)
today = date.today()

c1, c2, c3 = st.columns([2, 1, 1])
options = sorted(profiles, key=lambda c: profiles[c].name or c)
labels = {c: profiles[c].name or c for c in options}
chosen = c1.multiselect("Schools tracked", options, default=options[:min(6, len(options))],
                        format_func=lambda c: labels[c])
my_lsat = c2.number_input("Your LSAT", 120, 180, 165)
my_gpa = c3.number_input("Your GPA", 0.0, 4.33, 3.70, step=0.05)

if not chosen:
    st.caption("Pick at least one school above.")
    st.stop()

apps = {c: sample_application(c, profiles[c].cost_of_attendance, today) for c in chosen}


def net_after_offer(code: str) -> float | None:
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
    stat_card("Average net cost", money(sum(nets) / len(nets)) if nets else "—", "after sample scholarship offers") +
    stat_card("Average median LSAT", f"{sum(lsats) / len(lsats):.0f}" if lsats else "—", "across tracked schools") +
    stat_card("Next deadline", nxt[0].strftime("%b %d") if nxt else "—",
              f"{nxt[1]} · {labels[nxt[2]]}" if nxt else "nothing upcoming"))
st.markdown(f'<div class="lsc-grid4">{overview}</div>', unsafe_allow_html=True)

cards = "".join(school_card(
    name=labels[c], code=c, rank=ranks.get(c), status=apps[c].status,
    odds=admission_odds(my_lsat, my_gpa, profiles[c].lsat_50, profiles[c].gpa_50),
    lsat=profiles[c].lsat_50, gpa=profiles[c].gpa_50, cost=profiles[c].cost_of_attendance,
    offer=apps[c].scholarship_offer, net=net_after_offer(c), emp_rate=profiles[c].emp_rate,
    breakdown=profiles[c].emp_breakdown) for c in chosen)
st.markdown(f'<div class="lsc-grid2">{cards}</div>', unsafe_allow_html=True)

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

st.markdown('<h2 class="lsc-h2">Upcoming deadlines</h2>', unsafe_allow_html=True)
st.markdown(timeline([(d, label, labels[code]) for d, label, code in events], today), unsafe_allow_html=True)
st.markdown('<div class="lsc-note">Red: within 14 days. Amber: within 30. Green: later. Sample dates, '
            'regenerated relative to today.</div>', unsafe_allow_html=True)

with st.expander("Full numbers"):
    st.dataframe([{
        "School": labels[c], "Records": profiles[c].n, "Employment rate": profiles[c].emp_rate,
        "Bar passage rate": profiles[c].bar_pass_rate, "Median LSAT": profiles[c].lsat_50,
        "Median GPA": profiles[c].gpa_50, "Cost of attendance": profiles[c].cost_of_attendance,
        "Est. net cost (scholarship share)": profiles[c].est_net_cost, "Value index": profiles[c].value_index,
    } for c in chosen], hide_index=True)

with st.expander("How these numbers are calculated"):
    st.latex(r"\text{est. net cost} = \text{cost of attendance} \times (1 - \text{scholarship share})")
    st.latex(r"\text{value index} = \frac{\text{employment rate}}{\text{est. net cost} / 10{,}000}")
    st.write("Illustrative only. Cost is an invented sticker price; scholarship share is the share of the "
             "class with merit aid, not each student's discount. Reach/Target/Safe compares your LSAT and "
             "GPA with a school's medians and is not an admissions model. Employment types are the four "
             "categories the pipeline records (bar-passage-required, JD-advantage, other, unemployed).")
