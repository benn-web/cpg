"""Plotly chart components for the capital dependencies dashboard."""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from app.models import CapitalPanel, CapitalType, DependencyReport, MaterialityScore
from app.ui.theme import COLOUR_HIGH, COLOUR_MEDIUM, COLOUR_LOW, COLOUR_NA

# Colours for each capital type in the double materiality matrix
_CAPITAL_COLOURS = {
    CapitalType.NATURAL: "#2e7d32",   # green
    CapitalType.SOCIAL: "#1565c0",    # blue
    CapitalType.HUMAN: "#e65100",     # orange
}


_SCORE_COLOUR_MAP = {
    "high": COLOUR_HIGH,
    "medium": COLOUR_MEDIUM,
    "low": COLOUR_LOW,
    "not_applicable": COLOUR_NA,
}


def render_radar_chart(report: DependencyReport) -> go.Figure:
    """Radar chart showing aggregate materiality score per capital type."""
    categories = ["Natural Capital", "Social Capital", "Human Capital"]
    panels = [report.natural_capital, report.social_capital, report.human_capital]

    scores = []
    for panel in panels:
        if not panel.dependencies:
            scores.append(0)
        else:
            avg = sum(d.materiality_numeric for d in panel.dependencies) / len(panel.dependencies)
            scores.append(round(avg, 2))

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=scores + [scores[0]],
            theta=categories + [categories[0]],
            fill="toself",
            fillcolor="rgba(30, 136, 229, 0.3)",
            line=dict(color="rgba(30, 136, 229, 0.9)", width=2),
            name="Materiality",
        )
    )
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 3], tickvals=[1, 2, 3], ticktext=["Low", "Med", "High"]),
        ),
        showlegend=False,
        margin=dict(l=30, r=30, t=40, b=30),
        height=320,
        title=dict(text="Capital Dependency Profile", x=0.5, font=dict(size=14)),
    )
    return fig


def render_dependency_bars(panel: CapitalPanel) -> go.Figure:
    """Horizontal bar chart for dependencies in a single capital panel."""
    if not panel.dependencies:
        fig = go.Figure()
        fig.add_annotation(text="No material dependencies identified", showarrow=False)
        return fig

    labels = [d.dependency.label for d in panel.dependencies]
    scores = [d.materiality_numeric for d in panel.dependencies]
    colours = [_SCORE_COLOUR_MAP.get(d.materiality_score.value, COLOUR_NA) for d in panel.dependencies]

    fig = go.Figure(
        go.Bar(
            x=scores,
            y=labels,
            orientation="h",
            marker_color=colours,
            text=[d.materiality_score.value.upper() for d in panel.dependencies],
            textposition="inside",
        )
    )
    fig.update_layout(
        xaxis=dict(range=[0, 3.5], tickvals=[1, 2, 3], ticktext=["Low", "Medium", "High"]),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=10, t=10, b=10),
        height=max(250, len(labels) * 35),
        showlegend=False,
    )
    return fig


def render_score_distribution(panel: CapitalPanel) -> go.Figure:
    """Pie chart showing High/Medium/Low breakdown for a panel."""
    counts = {"High": panel.high_count, "Medium": panel.medium_count, "Low": panel.low_count}
    counts = {k: v for k, v in counts.items() if v > 0}

    if not counts:
        fig = go.Figure()
        fig.add_annotation(text="No data", showarrow=False)
        return fig

    fig = go.Figure(
        go.Pie(
            labels=list(counts.keys()),
            values=list(counts.values()),
            marker_colors=[COLOUR_HIGH, COLOUR_MEDIUM, COLOUR_LOW][: len(counts)],
            hole=0.4,
        )
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=200,
        showlegend=True,
        legend=dict(orientation="h", y=-0.1),
    )
    return fig


def render_double_materiality_matrix(report: DependencyReport) -> go.Figure:
    """
    Scatter plot placing each scored dependency at (financial materiality, impact materiality).
    Quadrant lines at 1.5 divide the space into four zones:
      top-right  = Doubly Material
      top-left   = Impact only
      bottom-right = Risk (Financial) only
      bottom-left  = Low priority
    Points are coloured by capital type; LLM-adjusted points use a diamond marker.
    """
    panels = [
        (report.natural_capital, CapitalType.NATURAL),
        (report.social_capital, CapitalType.SOCIAL),
        (report.human_capital, CapitalType.HUMAN),
    ]

    traces: dict[CapitalType, dict] = {
        cap_type: {"x": [], "y": [], "text": [], "symbol": [], "esrs": []}
        for _, cap_type in panels
    }

    for panel, cap_type in panels:
        for scored in panel.dependencies:
            d = traces[cap_type]
            d["x"].append(scored.materiality_numeric + (0.05 if scored.llm_adjusted else 0))
            d["y"].append(scored.impact_numeric + (0.05 if scored.llm_adjusted else 0))
            d["symbol"].append("diamond" if scored.llm_adjusted else "circle")
            esrs = scored.dependency.esrs_topic or ""
            d["text"].append(
                f"<b>{scored.dependency.label}</b><br>"
                f"ESRS: {esrs}<br>"
                f"Financial: {scored.materiality_score.value.upper()}<br>"
                f"Impact: {scored.impact_score.value.upper()}<br>"
                f"IRO: {scored.iro_type}"
            )
            d["esrs"].append(esrs)

    fig = go.Figure()

    label_map = {
        CapitalType.NATURAL: "Natural Capital",
        CapitalType.SOCIAL: "Social Capital",
        CapitalType.HUMAN: "Human Capital",
    }

    for cap_type, d in traces.items():
        if not d["x"]:
            continue
        colour = _CAPITAL_COLOURS[cap_type]
        fig.add_trace(
            go.Scatter(
                x=d["x"],
                y=d["y"],
                mode="markers+text",
                marker=dict(
                    size=12,
                    color=colour,
                    symbol=d["symbol"],
                    line=dict(width=1, color="white"),
                    opacity=0.85,
                ),
                text=["" for _ in d["x"]],
                hovertext=d["text"],
                hoverinfo="text",
                name=label_map[cap_type],
                legendgroup=label_map[cap_type],
            )
        )

    # Quadrant divider lines
    threshold = 1.5
    line_style = dict(color="rgba(100,100,100,0.4)", width=1.5, dash="dash")
    fig.add_shape(type="line", x0=threshold, x1=threshold, y0=-0.2, y1=3.4, line=line_style)
    fig.add_shape(type="line", x0=-0.2, x1=3.4, y0=threshold, y1=threshold, line=line_style)

    # Quadrant background shading
    fig.add_shape(type="rect", x0=threshold, x1=3.4, y0=threshold, y1=3.4,
                  fillcolor="rgba(213,0,0,0.06)", line_width=0)
    fig.add_shape(type="rect", x0=-0.2, x1=threshold, y0=threshold, y1=3.4,
                  fillcolor="rgba(255,143,0,0.06)", line_width=0)
    fig.add_shape(type="rect", x0=threshold, x1=3.4, y0=-0.2, y1=threshold,
                  fillcolor="rgba(255,143,0,0.06)", line_width=0)
    fig.add_shape(type="rect", x0=-0.2, x1=threshold, y0=-0.2, y1=threshold,
                  fillcolor="rgba(158,158,158,0.06)", line_width=0)

    # Quadrant labels
    for x, y, label in [
        (2.6, 3.2, "⬛ Doubly Material"),
        (0.5, 3.2, "Impact only"),
        (2.6, 0.3, "Risk only"),
        (0.5, 0.3, "Low priority"),
    ]:
        fig.add_annotation(
            x=x, y=y, text=label, showarrow=False,
            font=dict(size=10, color="rgba(80,80,80,0.7)"),
        )

    fig.update_layout(
        xaxis=dict(
            title="Financial Materiality (outside-in)",
            range=[-0.2, 3.4],
            tickvals=[1, 2, 3],
            ticktext=["Low", "Medium", "High"],
            gridcolor="rgba(200,200,200,0.3)",
        ),
        yaxis=dict(
            title="Impact Materiality (inside-out)",
            range=[-0.2, 3.4],
            tickvals=[1, 2, 3],
            ticktext=["Low", "Medium", "High"],
            gridcolor="rgba(200,200,200,0.3)",
        ),
        legend=dict(
            orientation="h", y=-0.15, x=0.5, xanchor="center",
            font=dict(size=11),
        ),
        margin=dict(l=60, r=20, t=50, b=80),
        height=480,
        title=dict(
            text="Double Materiality Matrix",
            x=0.5, font=dict(size=14),
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


def render_materiality_heatmap(report: DependencyReport) -> go.Figure:
    """Heatmap of all dependencies × capital type."""
    panels = {
        "Natural": report.natural_capital.dependencies,
        "Social": report.social_capital.dependencies,
        "Human": report.human_capital.dependencies,
    }

    # Collect all unique dependency labels
    all_labels: list[str] = []
    for deps in panels.values():
        for d in deps:
            if d.dependency.label not in all_labels:
                all_labels.append(d.dependency.label)

    # Build matrix
    matrix = []
    col_labels = list(panels.keys())
    for label in all_labels:
        row = []
        for cap_type, deps in panels.items():
            score = next(
                (d.materiality_numeric for d in deps if d.dependency.label == label), 0
            )
            row.append(score)
        matrix.append(row)

    df = pd.DataFrame(matrix, index=all_labels, columns=col_labels)

    fig = px.imshow(
        df,
        color_continuous_scale=[(0, COLOUR_NA), (0.33, COLOUR_LOW), (0.66, COLOUR_MEDIUM), (1.0, COLOUR_HIGH)],
        range_color=[0, 3],
        aspect="auto",
        labels={"color": "Materiality"},
    )
    fig.update_coloraxes(
        colorbar=dict(
            tickvals=[0, 1, 2, 3],
            ticktext=["N/A", "Low", "Medium", "High"],
        )
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        height=max(300, len(all_labels) * 22 + 60),
        xaxis=dict(side="top"),
        title=dict(text="Materiality Heatmap", x=0.5, font=dict(size=13)),
    )
    return fig
