"""Interactive Altair charts. Builders return chart objects (no Streamlit import), so the
specs are testable. Navy/cream palette matches dashboard/ui.py."""

from __future__ import annotations

import altair as alt

NAVY, SLATE, SAND, GRID = "#1F2F54", "#6B7080", "#C9A35C", "#ECE8DF"


def short_name(name: str) -> str:
    for suffix in (" School of Law", " College of Law", " University", " State"):
        name = name.replace(suffix, "")
    return name.strip()


def value_bubble_chart(points: list[dict], height: int = 440) -> alt.LayerChart | None:
    """points: school, code, net_cost, emp_rate, class_size, value_index, rank.
    x = estimated net cost, y = employment rate, bubble = class size, color = value index.
    Dashed lines mark the group averages; the top-left quadrant is the sweet spot."""
    pts = [p for p in points if p.get("net_cost") is not None and p.get("emp_rate") is not None]
    if not pts:
        return None
    rows = [{**p, "label": short_name(p["school"]), "class_size": p.get("class_size") or 200,
             "value_index": p.get("value_index") or 0} for p in pts]
    mean_x = sum(p["net_cost"] for p in rows) / len(rows)
    mean_y = sum(p["emp_rate"] for p in rows) / len(rows)
    xs, ys = [p["net_cost"] for p in rows], [p["emp_rate"] for p in rows]
    x_scale = alt.Scale(domain=[min(xs) * 0.85, max(xs) * 1.08], nice=True)
    y_scale = alt.Scale(domain=[max(0, min(ys) - 0.08), min(1, max(ys) + 0.08)])

    hover = alt.selection_point(on="mouseover", fields=["code"], empty=False, nearest=True)
    base = alt.Chart(alt.Data(values=rows)).encode(
        x=alt.X("net_cost:Q", title="Estimated net cost ($)", scale=x_scale, axis=alt.Axis(format="$,.0f")),
        y=alt.Y("emp_rate:Q", title="Employment rate", scale=y_scale, axis=alt.Axis(format=".0%")))

    bubbles = base.mark_circle(stroke="white", strokeWidth=2).encode(
        size=alt.Size("class_size:Q", scale=alt.Scale(range=[260, 1900]), legend=None),
        color=alt.Color("value_index:Q", title="Value index",
                        scale=alt.Scale(range=["#B9C6E4", "#5C77B4", NAVY]), legend=alt.Legend(orient="bottom")),
        opacity=alt.condition(hover, alt.value(1), alt.value(0.72)),
        tooltip=[alt.Tooltip("school:N", title="School"), alt.Tooltip("code:N", title="Code"),
                 alt.Tooltip("rank:Q", title="Rank (sample)"),
                 alt.Tooltip("emp_rate:Q", title="Employment rate", format=".1%"),
                 alt.Tooltip("net_cost:Q", title="Est. net cost", format="$,.0f"),
                 alt.Tooltip("value_index:Q", title="Value index", format=".3f"),
                 alt.Tooltip("class_size:Q", title="Class size", format=".0f")],
    ).add_params(hover)

    labels = base.mark_text(dy=-22, fontSize=11.5, fontWeight=600, font="Inter", color=NAVY).encode(text="label:N")
    vline = alt.Chart(alt.Data(values=[{"x": mean_x}])).mark_rule(strokeDash=[5, 5], color=SLATE, opacity=0.5).encode(x=alt.X("x:Q", scale=x_scale))
    hline = alt.Chart(alt.Data(values=[{"y": mean_y}])).mark_rule(strokeDash=[5, 5], color=SLATE, opacity=0.5).encode(y=alt.Y("y:Q", scale=y_scale))
    note = alt.Chart(alt.Data(values=[{"t": "↖ higher employment, lower cost"}])).mark_text(
        align="left", baseline="top", dx=10, dy=8, fontSize=11, font="Inter", color=SAND, fontWeight=600
    ).encode(text="t:N", x=alt.value(0), y=alt.value(0))

    return (alt.layer(vline, hline, bubbles.interactive(), labels, note)
            .properties(height=height)
            .configure_view(stroke=None, fill="#FFFFFF")
            .configure_axis(gridColor=GRID, domainColor="#D8D2C4", labelFont="Inter", titleFont="Inter",
                            labelColor=SLATE, titleColor=SLATE, titleFontWeight=500)
            .configure_legend(labelFont="Inter", titleFont="Inter", labelColor=SLATE, titleColor=SLATE))
