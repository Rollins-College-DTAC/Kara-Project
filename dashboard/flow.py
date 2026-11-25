"""Builds the Live Run page's flow-chart DOT graph (references/dashboard.md).

Pure string building, no Streamlit dependency, so the logic is testable without running the app.
Colors come from run_log.status: grey waiting (the step hasn't logged a row for this run yet),
blue running, green done, amber held or warning, red failed. The branch not taken is dashed.
"""

from __future__ import annotations

STEPS = [
    ("detect", "Detect"), ("land", "Land\\n(TinyDB)"), ("redact", "Redact"), ("route", "Route"),
    ("classify", "Classify"), ("extract", "Extract"), ("validate", "Validate"),
    ("load", "Load\\n(SQLite)"), ("decide", "Decide"),
]
COLOR = {"running": "dodgerblue", "ok": "forestgreen", "warning": "goldenrod",
         "held": "goldenrod", "failed": "firebrick"}
WAITING_COLOR = "grey70"
MAX_LABEL = 60


def _short(text: str, n: int = MAX_LABEL) -> str:
    text = (text or "").replace('"', "'").replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def build_dot(run_log_rows: list[dict], decision: dict | None) -> str:
    by_step = {r["step"]: r for r in run_log_rows}
    lines = ["digraph flow {", '  rankdir=LR; node [shape=box, style=filled, fontname="Helvetica"];']

    prev = None
    for step_name, label in STEPS:
        row = by_step.get(step_name)
        color = COLOR.get(row["status"], WAITING_COLOR) if row else WAITING_COLOR
        extra = f"\\n{_short(row['message'])}" if row and row.get("message") else ""
        lines.append(f'  "{step_name}" [label="{label}{extra}", fillcolor="{color}", fontcolor=white];')
        if prev:
            lines.append(f'  "{prev}" -> "{step_name}";')
        prev = step_name

    act_row = by_step.get("act")
    fired = bool(decision and decision.get("fired"))
    publish_color = COLOR["ok"] if act_row and not fired else WAITING_COLOR
    hold_color = COLOR["held"] if act_row and fired else WAITING_COLOR
    lines.append(f'  "publish" [label="Publish", fillcolor="{publish_color}", fontcolor=white];')
    lines.append(f'  "hold" [label="Hold and alert", fillcolor="{hold_color}", fontcolor=white];')
    lines.append(f'  "decide" -> "publish"{" [style=dashed]" if fired else ""};')
    lines.append(f'  "decide" -> "hold"{"" if fired else " [style=dashed]"};')
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------- animated SVG version

NODE_W, NODE_H, GAP, X0, Y0 = 98, 58, 14, 14, 56
STATUS_STYLE = {  # status -> (border, fill, text)
    "ok": ("#2F7A5A", "#E4F1EA", "#1F5A41"), "running": ("#3B6FD1", "#E3ECFB", "#27478C"),
    "warning": ("#9A6410", "#FAEFD6", "#6E4609"), "held": ("#9A6410", "#FAEFD6", "#6E4609"),
    "failed": ("#A83A48", "#F7E1E4", "#7C2631"), None: ("#D8D2C4", "#F3EFE7", "#8A8F9C"),
}


def _node(i: int, key: str, label: str, row: dict | None) -> str:
    x = X0 + i * (NODE_W + GAP)
    border, fill, text = STATUS_STYLE.get(row["status"] if row else None, STATUS_STYLE[None])
    sub = ""
    if row:
        sub = f'{row["rows_out"]} rows' if row.get("rows_out") is not None else row["status"]
    cls = ' class="lsc-flow-pulse"' if row and row["status"] == "running" else ""
    label = label.replace("\\n", " ")
    return (f'<g{cls}><rect x="{x}" y="{Y0}" width="{NODE_W}" height="{NODE_H}" rx="12" fill="{fill}" stroke="{border}" stroke-width="1.6"/>'
            f'<text x="{x + NODE_W / 2}" y="{Y0 + 25}" text-anchor="middle" font-family="Inter,sans-serif" font-size="12.5" '
            f'font-weight="600" fill="{text}">{label}</text>'
            f'<text x="{x + NODE_W / 2}" y="{Y0 + 43}" text-anchor="middle" font-family="Inter,sans-serif" font-size="10.5" '
            f'fill="{text}" opacity=".8">{sub}</text></g>')


def pipeline_svg(run_log_rows: list[dict], decision: dict | None) -> str:
    """The same information as build_dot, drawn as an animated SVG: finished edges carry flowing
    dashes, a running step pulses, and the Decide branch not taken is dashed and faded."""
    by_step = {r["step"]: r for r in run_log_rows}
    parts = []
    mid = Y0 + NODE_H / 2
    for i, (key, label) in enumerate(STEPS):
        if i:
            x1 = X0 + (i - 1) * (NODE_W + GAP) + NODE_W
            done = STEPS[i - 1][0] in by_step and key in by_step
            color = "#2F7A5A" if done else "#D8D2C4"
            cls = ' class="lsc-flow-edge"' if done else ""
            parts.append(f'<line{cls} x1="{x1}" y1="{mid}" x2="{x1 + GAP}" y2="{mid}" stroke="{color}" stroke-width="2.4"/>')
        parts.append(_node(i, key, label, by_step.get(key)))

    last_x = X0 + (len(STEPS) - 1) * (NODE_W + GAP) + NODE_W
    bx = last_x + 44
    act = by_step.get("act")
    fired = bool(decision and decision.get("fired"))
    branches = [("Publish", Y0 - 34, "ok" if act and not fired else None, not fired),
                ("Hold and alert", Y0 + NODE_H + 4, "held" if act and fired else None, fired)]
    for name, by, status, taken in branches:
        border, fill, text = STATUS_STYLE[status]
        cy = by + 15
        dash = "" if taken else ' stroke-dasharray="4 4" opacity=".55"'
        color = border if taken and act else "#D8D2C4"
        parts.append(f'<path d="M{last_x} {mid} C{last_x + 22} {mid}, {last_x + 14} {cy}, {bx} {cy}" fill="none" '
                     f'stroke="{color}" stroke-width="2.2"{dash}/>')
        parts.append(f'<g><rect x="{bx}" y="{by}" width="132" height="30" rx="15" fill="{fill}" stroke="{border}" stroke-width="1.6"{dash}/>'
                     f'<text x="{bx + 66}" y="{by + 19.5}" text-anchor="middle" font-family="Inter,sans-serif" font-size="12" '
                     f'font-weight="600" fill="{text}">{name}</text></g>')
    width = bx + 132 + 14
    return f'<div class="lsc-flow"><svg viewBox="0 0 {width} {Y0 + NODE_H + 54}" role="img" aria-label="Pipeline status">{"".join(parts)}</svg></div>'
