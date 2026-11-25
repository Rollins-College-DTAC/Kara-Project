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

.stApp [data-testid="stHeading"] h1, .stApp [data-testid="stHeading"] h2, .stApp [data-testid="stHeading"] h3,
.stApp .stMarkdown h1, .stApp .stMarkdown h2, .stApp .stMarkdown h3 { font-family: 'Playfair Display', Georgia, serif !important; color: #1F2F54 !important; letter-spacing: -.01em; }
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #1F2F54 0%, #141E38 100%); }
section[data-testid="stSidebar"] a, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] p { color: #E8E2D4 !important; }
section[data-testid="stSidebar"] a[aria-current="page"] { background: rgba(255,255,255,.14) !important; border-radius: 8px; }
section[data-testid="stSidebar"] a:hover { background: rgba(255,255,255,.08) !important; border-radius: 8px; }
[data-testid="stMetric"] { background: #fff; border: 1px solid #E6DFD3; border-radius: 12px; padding: 14px 16px; box-shadow: 0 1px 2px rgba(31,47,84,.04); transition: transform .2s ease, box-shadow .2s ease; }
[data-testid="stMetric"]:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(31,47,84,.10); }
[data-testid="stExpander"] { background: #fff; border: 1px solid #E6DFD3 !important; border-radius: 12px; }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; border: 1px solid #E6DFD3; }
.stApp .stButton button, .stApp .stDownloadButton button { border-radius: 999px; border: 1px solid #1F2F54; color: #1F2F54; transition: all .2s ease; }
.stApp .stButton button:hover { background: #1F2F54; color: #fff; }
@keyframes rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes growx { from { transform: scaleX(0); } }
@keyframes ringin { from { stroke-dashoffset: var(--c); } }
@keyframes flowdash { to { stroke-dashoffset: -24; } }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
@keyframes drift { 0% { transform: translate(0,0); } 50% { transform: translate(-30px,18px); } 100% { transform: translate(0,0); } }
@property --n { syntax: '<integer>'; initial-value: 0; inherits: false; }
@keyframes countup { from { --n: 0; } }
.cu { --n: var(--to); animation: countup 1.4s cubic-bezier(.2,.8,.2,1) both; counter-reset: num var(--n); }
.cu::after { content: counter(num); }
.stApp .block-container > div { animation: rise .5s ease both; }
.lsc-stat, .lsc-card { animation: rise .6s cubic-bezier(.2,.8,.2,1) both; transition: transform .25s ease, box-shadow .25s ease; }
.lsc-stat:hover, .lsc-card:hover { transform: translateY(-4px); box-shadow: 0 14px 30px rgba(31,47,84,.13); }
.lsc-grid4 > :nth-child(2), .lsc-grid2 > :nth-child(2) { animation-delay: .07s; }
.lsc-grid4 > :nth-child(3), .lsc-grid2 > :nth-child(3) { animation-delay: .14s; }
.lsc-grid4 > :nth-child(4), .lsc-grid2 > :nth-child(4) { animation-delay: .21s; }
.lsc-grid2 > :nth-child(5) { animation-delay: .28s; }
.lsc-grid2 > :nth-child(6) { animation-delay: .35s; }
.lsc-bar div { transform-origin: left; animation: growx 1.1s cubic-bezier(.2,.8,.2,1) both; }
.lsc-track div { transform-origin: left; animation: growx 1.2s cubic-bezier(.2,.8,.2,1) both; }
.lsc-body { display: grid; grid-template-columns: 96px 1fr 1fr; gap: 10px; align-items: center; margin-bottom: 16px; }
.lsc-ring { position: relative; width: 92px; height: 92px; }
.lsc-ring svg { transform: rotate(-90deg); }
.lsc-ring-fg { stroke-dasharray: var(--c); stroke-dashoffset: var(--off); animation: ringin 1.4s cubic-bezier(.2,.8,.2,1) both; stroke-linecap: round; }
.lsc-ring-txt { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.lsc-ring-txt b { font-size: 1.05rem; font-variant-numeric: tabular-nums; }
.lsc-ring-txt span { font-size: .58rem; text-transform: uppercase; letter-spacing: .06em; color: #6B7080; }
.lsc-hero { position: relative; overflow: hidden; border-radius: 20px; padding: 30px 34px 26px; color: #fff; margin-bottom: 1.6rem; background: linear-gradient(125deg, #1F2F54 0%, #2C4170 55%, #3E5A9A 100%); box-shadow: 0 18px 40px rgba(31,47,84,.22); }
.lsc-hero::before { content: ''; position: absolute; width: 380px; height: 380px; right: -90px; top: -150px; border-radius: 50%; background: radial-gradient(circle, rgba(255,255,255,.22), transparent 65%); animation: drift 14s ease-in-out infinite; }
.lsc-hero::after { content: ''; position: absolute; width: 300px; height: 300px; left: 30%; bottom: -190px; border-radius: 50%; background: radial-gradient(circle, rgba(201,163,92,.30), transparent 65%); animation: drift 18s ease-in-out infinite reverse; }
.lsc-hero-eyebrow { font-size: .72rem; text-transform: uppercase; letter-spacing: .14em; color: #C9A35C; font-weight: 600; position: relative; z-index: 1; }
.lsc-hero-title { font-family: 'Playfair Display', Georgia, serif; font-size: 2.5rem; font-weight: 700; margin: 4px 0 4px; letter-spacing: -.01em; position: relative; z-index: 1; }
.lsc-hero-sub { color: #CBD5EC; font-size: .92rem; max-width: 760px; position: relative; z-index: 1; }
.lsc-hero-kpis { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; margin-top: 20px; position: relative; z-index: 1; }
@media (max-width: 900px) { .lsc-hero-kpis { grid-template-columns: repeat(2, 1fr); } .lsc-body { grid-template-columns: 1fr 1fr; } .lsc-ring { grid-column: 1 / -1; margin: 0 auto; } }
.lsc-kpi { background: rgba(255,255,255,.09); border: 1px solid rgba(255,255,255,.16); border-radius: 12px; padding: 12px 14px; backdrop-filter: blur(4px); }
.lsc-kpi .lbl { font-size: .66rem; text-transform: uppercase; letter-spacing: .09em; color: #B7C4E4; }
.lsc-kpi .val { font-size: 1.65rem; font-weight: 600; font-variant-numeric: tabular-nums; margin-top: 2px; }
.lsc-kpi .sub { font-size: .72rem; color: #B7C4E4; }
.lsc-flow { background: #fff; border: 1px solid #E6DFD3; border-radius: 16px; padding: 14px 10px 6px; box-shadow: 0 1px 2px rgba(31,47,84,.04); }
.lsc-flow svg { width: 100%; height: auto; display: block; }
.lsc-flow-edge { stroke-dasharray: 6 6; animation: flowdash .9s linear infinite; }
.lsc-flow-pulse { animation: pulse 1.2s ease-in-out infinite; }
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


def stat_card(label: str, value: str, sub: str = "", count_to: int | None = None) -> str:
    sub_html = f'<div class="sub">{esc(sub)}</div>' if sub else ""
    shown = counter(count_to) if count_to is not None else esc(value)
    return f'<div class="lsc-stat"><div class="lbl">{esc(label)}</div><div class="val">{shown}</div>{sub_html}</div>'


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
    rank_txt = f" \u00b7 Rank #{rank} (sample)" if rank else ""
    pills = pill(status, status_tone(status)) + (pill(odds, odds_tone(odds)) if odds else "")
    lsat_gpa = f"{lsat:.0f} / {gpa:.2f}" if lsat is not None and gpa is not None else "\u2014"
    offer_sub = f"offer {money(offer)} of {money(cost)}" if offer else f"sticker {money(cost)}, no offer yet"
    body = (ring(emp_rate, employment_tone(emp_rate), "employed") +
            metric("LSAT / GPA medians", lsat_gpa, "median, current class") +
            metric("Net tuition", money(net), offer_sub, cost_tone(net)))
    return (f'<div class="lsc-card"><div class="lsc-head"><div><h3 class="lsc-name">{esc(name)}</h3>'
            f'<div class="lsc-sub">{esc(code)}{esc(rank_txt)}</div></div><div class="lsc-pills">{pills}</div></div>'
            f'<div class="lsc-body">{body}</div><div class="lsc-sec">Employment by type \u00b7 10 months post-grad</div>'
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


import math


def ring(value: float | None, tone: str, label: str) -> str:
    """Animated progress ring; the stroke draws itself in via CSS."""
    r = 38
    c = 2 * math.pi * r
    frac = 0.0 if value is None else max(0.0, min(1.0, value))
    color = tone_color(tone) if tone in ("good", "warn", "bad") else NAVY
    return (f'<div class="lsc-ring"><svg width="92" height="92" viewBox="0 0 92 92">'
            f'<circle cx="46" cy="46" r="{r}" fill="none" stroke="#ECE8DF" stroke-width="8"/>'
            f'<circle class="lsc-ring-fg" cx="46" cy="46" r="{r}" fill="none" stroke="{color}" stroke-width="8" '
            f'style="--c:{c:.2f};--off:{c * (1 - frac):.2f}"/></svg>'
            f'<div class="lsc-ring-txt"><b style="color:{color}">{pct(value)}</b><span>{esc(label)}</span></div></div>')


def counter(value: int) -> str:
    """An integer that counts up from zero on load (CSS only)."""
    return f'<span class="cu" style="--to:{int(value)}" aria-label="{int(value)}"></span>'


def hero(title: str, subtitle: str, kpis: list[tuple[str, str, str]], eyebrow: str = "Law School Outcomes Agent") -> str:
    """kpis: (label, value, sub). Values are escaped; pass counter() HTML via raw=... not supported here."""
    tiles = "".join(f'<div class="lsc-kpi"><div class="lbl">{esc(l)}</div><div class="val">{esc(v)}</div>'
                    f'<div class="sub">{esc(s)}</div></div>' for l, v, s in kpis)
    grid = f'<div class="lsc-hero-kpis">{tiles}</div>' if tiles else ""
    return (f'<div class="lsc-hero"><div class="lsc-hero-eyebrow">{esc(eyebrow)}</div>'
            f'<div class="lsc-hero-title">{esc(title)}</div><div class="lsc-hero-sub">{esc(subtitle)}</div>{grid}</div>')
