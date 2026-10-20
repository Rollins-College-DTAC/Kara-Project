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
