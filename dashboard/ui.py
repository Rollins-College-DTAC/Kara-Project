"""Presentation helpers for the Compare Schools page: design tokens, CSS, and pure HTML builders.

No Streamlit import, so every builder is a plain string function and testable. All text that
originates from data is HTML-escaped. HTML is emitted without newlines or indentation on purpose:
Streamlit's markdown renderer would otherwise treat indented lines as code blocks.
"""

from __future__ import annotations

import html
from datetime import date

NAVY = "#1F2F54"
GREEN, GREEN_BG = "#2F7A5A", "#E4F1EA"
AMBER, AMBER_BG = "#9A6410", "#FAEFD6"
CRIMSON, CRIMSON_BG = "#A83A48", "#F7E1E4"
NEUTRAL, NEUTRAL_BG = "#4A5163", "#ECE8DF"

TONES = {"good": (GREEN, GREEN_BG), "warn": (AMBER, AMBER_BG), "bad": (CRIMSON, CRIMSON_BG),
         "neutral": (NEUTRAL, NEUTRAL_BG), "navy": ("#FFFFFF", NAVY)}
EMP_COLORS = {"bar_required": NAVY, "jd_advantage": "#6C85B8", "other": "#D9CBA8", "unemployed": "#C9707B"}
EMP_LABELS = {"bar_required": "Bar-passage-required job", "jd_advantage": "JD-advantage job",
              "other": "Other", "unemployed": "Unemployed"}

CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Playfair+Display:wght@500;600;700&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Inter', system-ui, sans-serif; }
.stApp { background: #FAF7F2; }
.block-container { max-width: 1180px; padding-top: 2.2rem; }
.lsc-title { font-family: 'Playfair Display', Georgia, serif; font-size: 2.3rem; color: #1F2F54; margin: 0 0 .15rem 0; letter-spacing: -.01em; }
.lsc-tagline { color: #6B7080; font-size: .95rem; margin-bottom: 1.4rem; }
.lsc-num { font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; }
.lsc-grid4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 1.6rem; }
.lsc-grid2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-bottom: 1.6rem; }
@media (max-width: 900px) { .lsc-grid4 { grid-template-columns: repeat(2, 1fr); } .lsc-grid2 { grid-template-columns: 1fr; } }
.lsc-stat { background: #fff; border: 1px solid #E6DFD3; border-radius: 12px; padding: 16px 18px; }
.lsc-stat .lbl { font-size: .72rem; text-transform: uppercase; letter-spacing: .07em; color: #6B7080; }
.lsc-stat .val { font-size: 1.7rem; font-weight: 600; color: #1B1F2A; margin-top: 4px; font-variant-numeric: tabular-nums; }
.lsc-stat .sub { font-size: .8rem; color: #6B7080; margin-top: 2px; }
.lsc-card { background: #fff; border: 1px solid #E6DFD3; border-radius: 14px; padding: 20px 22px; box-shadow: 0 1px 2px rgba(31,47,84,.04); }
.lsc-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.lsc-name { font-family: 'Playfair Display', Georgia, serif; font-size: 1.28rem; font-weight: 600; color: #1F2F54; margin: 0; line-height: 1.25; }
.lsc-sub { font-size: .8rem; color: #6B7080; margin-top: 3px; }
.lsc-pills { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.lsc-pill { font-size: .72rem; font-weight: 600; padding: 3px 10px; border-radius: 999px; white-space: nowrap; }
.lsc-big3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px; }
.lsc-m { background: #FAF7F2; border-radius: 10px; padding: 10px 12px; }
.lsc-m .lbl { font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; color: #6B7080; }
.lsc-m .val { font-size: 1.12rem; font-weight: 600; margin-top: 3px; font-variant-numeric: tabular-nums; }
.lsc-m .sub { font-size: .72rem; color: #6B7080; margin-top: 2px; font-variant-numeric: tabular-nums; }
.lsc-bar { display: flex; height: 12px; border-radius: 6px; overflow: hidden; background: #ECE8DF; }
.lsc-legend { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 8px; font-size: .72rem; color: #4A5163; }
.lsc-legend i { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 5px; }
.lsc-sec { font-size: .72rem; text-transform: uppercase; letter-spacing: .07em; color: #6B7080; margin-bottom: 7px; }
.lsc-h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 1.5rem; color: #1F2F54; margin: 1.6rem 0 .6rem 0; }
.lsc-tl { background: #fff; border: 1px solid #E6DFD3; border-radius: 14px; padding: 8px 20px; }
.lsc-tl-row { display: grid; grid-template-columns: 96px 1fr 110px; gap: 14px; align-items: center; padding: 11px 0; border-bottom: 1px solid #F0EBE1; }
.lsc-tl-row:last-child { border-bottom: 0; }
.lsc-tl-date { font-size: .85rem; font-weight: 600; color: #1B1F2A; font-variant-numeric: tabular-nums; }
.lsc-tl-what { font-size: .9rem; color: #1B1F2A; }
.lsc-tl-what span { color: #6B7080; font-size: .78rem; display: block; }
.lsc-track { height: 8px; background: #ECE8DF; border-radius: 4px; overflow: hidden; }
.lsc-track div { height: 100%; border-radius: 4px; }
.lsc-note { font-size: .78rem; color: #6B7080; margin-top: 8px; }
.stApp h1.lsc-title, .stApp h2.lsc-h2, .stApp h3.lsc-name { font-family: 'Playfair Display', Georgia, serif !important; color: #1F2F54 !important; }
.stApp h1.lsc-title { font-weight: 700 !important; font-size: 2.3rem !important; }
.stApp h3.lsc-name { font-size: 1.28rem !important; font-weight: 600 !important; padding: 0 !important; }
.stApp h2.lsc-h2 { font-size: 1.5rem !important; font-weight: 600 !important; }
</style>"""


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def pill(text: str, tone: str = "neutral") -> str:
    fg, bg = TONES[tone]
    return f'<span class="lsc-pill" style="color:{fg};background:{bg}">{esc(text)}</span>'


def status_tone(status: str) -> str:
    return {"Accepted": "good", "Submitted": "navy", "Waitlisted": "warn", "Draft": "neutral"}.get(status, "neutral")


def odds_tone(odds: str | None) -> str:
    return {"Safe": "good", "Target": "navy", "Reach": "warn"}.get(odds or "", "neutral")


def employment_tone(rate: float | None) -> str:
    if rate is None:
        return "neutral"
    return "good" if rate >= 0.65 else "warn" if rate >= 0.5 else "bad"


def cost_tone(net_cost: float | None) -> str:
    if net_cost is None:
        return "neutral"
    return "good" if net_cost <= 25000 else "warn" if net_cost <= 40000 else "bad"


def money(value: float | None) -> str:
    return "—" if value is None else f"${value:,.0f}"


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def tone_color(tone: str) -> str:
    return {"good": GREEN, "warn": AMBER, "bad": CRIMSON}.get(tone, "#1B1F2A")


def metric(label: str, value: str, sub: str = "", tone: str = "neutral") -> str:
    color = tone_color(tone)
    sub_html = f'<div class="sub">{esc(sub)}</div>' if sub else ""
    return (f'<div class="lsc-m"><div class="lbl">{esc(label)}</div>'
            f'<div class="val" style="color:{color}">{esc(value)}</div>{sub_html}</div>')


def stat_card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="sub">{esc(sub)}</div>' if sub else ""
    return f'<div class="lsc-stat"><div class="lbl">{esc(label)}</div><div class="val">{esc(value)}</div>{sub_html}</div>'


def employment_bar(breakdown: dict | None) -> str:
    if not breakdown:
        return '<div class="lsc-note">No employment breakdown yet.</div>'
    total = sum(breakdown.values()) or 1
    segments = "".join(
        f'<div title="{esc(EMP_LABELS[k])}: {v / total * 100:.1f}%" style="width:{v / total * 100:.2f}%;background:{EMP_COLORS[k]}"></div>'
        for k, v in breakdown.items() if k in EMP_COLORS)
    legend = "".join(
        f'<span><i style="background:{EMP_COLORS[k]}"></i>{esc(EMP_LABELS[k])} '
        f'<b class="lsc-num">{v / total * 100:.0f}%</b></span>' for k, v in breakdown.items() if k in EMP_COLORS)
    return f'<div class="lsc-bar">{segments}</div><div class="lsc-legend">{legend}</div>'


def school_card(*, name: str, code: str, rank: int | None, status: str, odds: str | None, lsat: float | None,
                gpa: float | None, cost: float | None, offer: float | None, net: float | None,
                emp_rate: float | None, breakdown: dict | None) -> str:
    rank_txt = f" · Rank #{rank} (sample)" if rank else ""
    pills = pill(status, status_tone(status)) + (pill(odds, odds_tone(odds)) if odds else "")
    lsat_gpa = f"{lsat:.0f} / {gpa:.2f}" if lsat is not None and gpa is not None else "—"
    offer_sub = f"offer {money(offer)} of {money(cost)}" if offer else f"sticker {money(cost)}, no offer yet"
    big3 = (metric("LSAT / GPA medians", lsat_gpa) +
            metric("Net tuition", money(net), offer_sub, cost_tone(net)) +
            metric("Employment rate", pct(emp_rate), "10 months post-grad", employment_tone(emp_rate)))
    return (f'<div class="lsc-card"><div class="lsc-head"><div><h3 class="lsc-name">{esc(name)}</h3>'
            f'<div class="lsc-sub">{esc(code)}{esc(rank_txt)}</div></div><div class="lsc-pills">{pills}</div></div>'
            f'<div class="lsc-big3">{big3}</div><div class="lsc-sec">Employment by type</div>'
            f'{employment_bar(breakdown)}</div>')


def timeline(events: list[tuple[date, str, str]], today: date, horizon_days: int = 120) -> str:
    """events: (due date, deadline label, school name), soonest first."""
    if not events:
        return '<div class="lsc-tl"><div class="lsc-note">No upcoming deadlines.</div></div>'
    rows = []
    for due, label, school in events:
        days = (due - today).days
        tone = "bad" if days <= 14 else "warn" if days <= 30 else "good"
        width = max(4, min(100, round(days / horizon_days * 100)))
        when = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
        rows.append(
            f'<div class="lsc-tl-row"><div class="lsc-tl-date">{due.strftime("%b %d")}</div>'
            f'<div class="lsc-tl-what">{esc(label)}<span>{esc(school)} · {when}</span></div>'
            f'<div class="lsc-track"><div style="width:{width}%;background:{tone_color(tone)}"></div></div></div>')
    return f'<div class="lsc-tl">{"".join(rows)}</div>'
