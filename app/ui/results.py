"""Results dashboard UI components."""
from __future__ import annotations

from typing import Union

import pandas as pd
import streamlit as st

from app.export import to_json, to_csv, to_excel, flatten_report
from app.models import (
    CapitalPanel,
    CompanyProfile,
    DependencyReport,
    EnrichedReport,
    MaterialityScore,
)
from app.ui.theme import (
    COLOUR_HIGH, COLOUR_MEDIUM, COLOUR_LOW, COLOUR_NA,
    format_market_cap, score_badge, MATERIALITY_COLOURS,
)
from app.ui import charts

AnyReport = Union[DependencyReport, EnrichedReport]


def _get_base(report: AnyReport) -> DependencyReport:
    return report.base_report if isinstance(report, EnrichedReport) else report


def render_company_card(company: CompanyProfile, sasb_code: str, sasb_confidence: str) -> None:
    st.markdown(
        f"""
<div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:16px;margin-bottom:16px">
  <h3 style="margin:0 0 4px 0">{company.name} &nbsp;
    <span style="font-size:0.85em;color:#555;font-weight:normal">{company.ticker}</span>
  </h3>
  <p style="margin:2px 0;font-size:0.9em;color:#333">
    <b>Sector:</b> {company.gics_sector} &nbsp;|&nbsp;
    <b>Industry:</b> {company.gics_industry} &nbsp;|&nbsp;
    <b>Market Cap:</b> {format_market_cap(company.market_cap, company.currency)}
  </p>
  <p style="margin:2px 0;font-size:0.85em;color:#555">
    <b>SASB:</b> {sasb_code} &nbsp;
    <span style="background:{'#2e7d32' if sasb_confidence == 'high' else '#f57c00' if sasb_confidence == 'medium' else '#c62828'};
      color:white;padding:1px 6px;border-radius:3px;font-size:0.8em">{sasb_confidence.upper()} confidence</span>
  </p>
</div>
""",
        unsafe_allow_html=True,
    )

    if company.description:
        with st.expander("Company description", expanded=False):
            st.write(company.description)


def render_metrics_row(report: DependencyReport) -> None:
    cols = st.columns(3)
    for col, panel, label in zip(
        cols,
        [report.natural_capital, report.social_capital, report.human_capital],
        ["Natural Capital", "Social Capital", "Human Capital"],
    ):
        with col:
            st.markdown(f"**{label}**")
            c1, c2, c3 = st.columns(3)
            c1.metric("HIGH", panel.high_count, delta=None)
            c2.metric("MED", panel.medium_count, delta=None)
            c3.metric("LOW", panel.low_count, delta=None)


def _panel_to_dataframe(panel: CapitalPanel) -> pd.DataFrame:
    rows = []
    for scored in panel.dependencies:
        rows.append(
            {
                "Dependency": scored.dependency.label + (" ⚡" if scored.llm_adjusted else ""),
                "Category": scored.dependency.category,
                "Subcategory": scored.dependency.subcategory,
                "Materiality": scored.materiality_score.value.upper(),
                "Score": scored.materiality_numeric,
                "Rationale": scored.rationale,
            }
        )
    return pd.DataFrame(rows)


def _style_materiality(val: str) -> str:
    colour_map = {
        "HIGH": f"background-color:{COLOUR_HIGH};color:white;font-weight:bold",
        "MEDIUM": f"background-color:{COLOUR_MEDIUM};color:white;font-weight:bold",
        "LOW": f"background-color:{COLOUR_LOW};color:white;font-weight:bold",
    }
    return colour_map.get(val.upper(), "")


def render_capital_panel(panel: CapitalPanel, panel_name: str, show_chart: bool = True) -> None:
    if not panel.dependencies:
        st.info(f"No material {panel_name.lower()} dependencies identified for this sector.")
        return

    df = _panel_to_dataframe(panel)

    styled = df.style.map(_style_materiality, subset=["Materiality"])

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=3, format="%d"
            ),
            "Rationale": st.column_config.TextColumn("Rationale", width="large"),
        },
    )

    # Expandable details for each dependency
    with st.expander("Dependency details & indicators", expanded=False):
        for scored in panel.dependencies:
            dep = scored.dependency
            colour = MATERIALITY_COLOURS[scored.materiality_score]
            st.markdown(
                f"**{dep.label}** &nbsp;"
                f'<span style="background:{colour};color:white;padding:1px 8px;border-radius:3px;font-size:0.8em">'
                f"{scored.materiality_score.value.upper()}</span>"
                + (" &nbsp;⚡ *LLM adjusted*" if scored.llm_adjusted else ""),
                unsafe_allow_html=True,
            )
            st.caption(dep.description)
            if dep.indicators:
                st.markdown("**Key indicators:** " + " · ".join(dep.indicators))
            if dep.tnfd_ecosystem_service:
                st.caption(f"TNFD ecosystem service: {dep.tnfd_ecosystem_service}")
            if scored.llm_adjustment_note:
                st.info(f"⚡ {scored.llm_adjustment_note}")
            st.divider()

    if show_chart:
        bar_fig = charts.render_dependency_bars(panel)
        st.plotly_chart(bar_fig, use_container_width=True)


def render_overview_tab(report: AnyReport) -> None:
    base = _get_base(report)
    col1, col2 = st.columns([1, 1])
    with col1:
        radar = charts.render_radar_chart(base)
        st.plotly_chart(radar, use_container_width=True)
    with col2:
        heatmap = charts.render_materiality_heatmap(base)
        st.plotly_chart(heatmap, use_container_width=True)

    if isinstance(report, EnrichedReport) and report.llm_narrative:
        st.markdown("### Claude Analysis")
        st.write(report.llm_narrative)
        if report.llm_evidence_sources:
            st.markdown("**Evidence sources:**")
            for src in report.llm_evidence_sources:
                st.markdown(f"- {src}")

        if report.llm_additions:
            st.markdown("### ⚡ LLM-Identified Dependencies")
            for ft in report.llm_additions:
                colour = MATERIALITY_COLOURS[ft.materiality_score]
                st.markdown(
                    f"**{ft.label}** ({ft.capital_type.value}) &nbsp;"
                    f'<span style="background:{colour};color:white;padding:1px 8px;border-radius:3px;font-size:0.8em">'
                    f"{ft.materiality_score.value.upper()}</span>",
                    unsafe_allow_html=True,
                )
                st.caption(ft.description)
                st.write(ft.llm_rationale)
                st.divider()


def render_export_row(report: AnyReport, company_name: str) -> None:
    st.markdown("---")
    st.markdown("#### Export Results")
    safe_name = company_name.replace(" ", "_").replace("/", "-")[:20]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            label="⬇ JSON",
            data=to_json(report),
            file_name=f"{safe_name}_capital_dependencies.json",
            mime="application/json",
            use_container_width=True,
        )
    with c2:
        st.download_button(
            label="⬇ CSV",
            data=to_csv(report),
            file_name=f"{safe_name}_capital_dependencies.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with c3:
        st.download_button(
            label="⬇ Excel",
            data=to_excel(report),
            file_name=f"{safe_name}_capital_dependencies.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


def render_results(report: AnyReport) -> None:
    base = _get_base(report)
    company = base.company

    render_company_card(company, base.sasb_mapping.sasb_industry_code, base.sasb_mapping.confidence)
    render_metrics_row(base)

    st.markdown("---")
    tabs = st.tabs(["🌿 Natural Capital", "🤝 Social Capital", "👷 Human Capital", "📊 Overview"])

    with tabs[0]:
        render_capital_panel(base.natural_capital, "Natural Capital")
    with tabs[1]:
        render_capital_panel(base.social_capital, "Social Capital")
    with tabs[2]:
        render_capital_panel(base.human_capital, "Human Capital")
    with tabs[3]:
        render_overview_tab(report)

    render_export_row(report, company.name)
