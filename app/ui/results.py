"""Results dashboard UI components."""
from __future__ import annotations

from typing import Union

import pandas as pd
import streamlit as st

from app.dependency_engine import apply_stakeholder_overrides
from app.export import to_json, to_csv, to_excel, to_iro_register_csv, flatten_report
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
from app.ui import stakeholder as stakeholder_ui

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
            if dep.sources:
                st.markdown("**Source references:**")
                for src in dep.sources:
                    st.markdown(f"- {src}")
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


def _iro_register_dataframe(base: DependencyReport) -> pd.DataFrame:
    """Build the IRO register table for display."""
    rows = []
    for panel in [base.natural_capital, base.social_capital, base.human_capital]:
        for scored in panel.dependencies:
            dep = scored.dependency
            rows.append({
                "ESRS": dep.esrs_topic or "–",
                "Label": dep.label,
                "Capital": panel.capital_type.value.title(),
                "Category": dep.category,
                "IRO Type": scored.iro_type,
                "Financial": scored.materiality_score.value.upper(),
                "Fin Score": scored.materiality_numeric,
                "Impact": scored.impact_score.value.upper(),
                "Imp Score": scored.impact_numeric,
                "Doubly Material": "✓" if scored.doubly_material else "",
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            ["Doubly Material", "Fin Score", "Imp Score"],
            ascending=[False, False, False],
        ).reset_index(drop=True)
    return df


def _style_iro_cell(val: str) -> str:
    colour_map = {
        "HIGH": f"background-color:{COLOUR_HIGH};color:white;font-weight:bold",
        "MEDIUM": f"background-color:{COLOUR_MEDIUM};color:white;font-weight:bold",
        "LOW": f"background-color:{COLOUR_LOW};color:white;font-weight:bold",
    }
    return colour_map.get(val, "")


def render_double_materiality_tab(report: AnyReport) -> None:
    """Render the Double Materiality tab: matrix, summary, IRO register, stakeholder panel."""
    base = _get_base(report)

    st.markdown(
        "Double materiality assesses both **financial materiality** (outside-in: how "
        "the external world affects the company) and **impact materiality** (inside-out: "
        "how the company affects natural, social, and human capital). Required under CSRD/ESRS."
    )

    # Apply any existing stakeholder overrides from session state
    existing_overrides = _collect_existing_overrides(base)
    if existing_overrides:
        base = apply_stakeholder_overrides(base, existing_overrides)

    # Summary counts
    all_scored = (
        list(base.natural_capital.dependencies)
        + list(base.social_capital.dependencies)
        + list(base.human_capital.dependencies)
    )
    doubly = sum(1 for d in all_scored if d.doubly_material)
    risk_only = sum(1 for d in all_scored if d.iro_type == "Risk" and not d.doubly_material)
    impact_only = sum(1 for d in all_scored if d.iro_type == "Impact" and not d.doubly_material)
    low_priority = sum(1 for d in all_scored if d.iro_type == "Low priority")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Doubly Material", doubly, help="Material on both financial and impact dimensions")
    c2.metric("Risk (Financial) only", risk_only, help="Material financially but low impact")
    c3.metric("Impact only", impact_only, help="High impact but low financial materiality")
    c4.metric("Low priority", low_priority, help="Low on both dimensions")

    st.markdown("---")

    # Double materiality matrix
    matrix_fig = charts.render_double_materiality_matrix(base)
    st.plotly_chart(matrix_fig, use_container_width=True)

    st.markdown("---")
    st.markdown("### IRO Register")
    st.caption(
        "Impacts, Risks and Opportunities register. "
        "Sorted by doubly-material items first, then by financial materiality score."
    )

    iro_df = _iro_register_dataframe(base)
    if not iro_df.empty:
        styled = iro_df.style.map(_style_iro_cell, subset=["Financial", "Impact"])
        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Fin Score": st.column_config.ProgressColumn("Fin", min_value=0, max_value=3, format="%d"),
                "Imp Score": st.column_config.ProgressColumn("Imp", min_value=0, max_value=3, format="%d"),
                "Label": st.column_config.TextColumn("Dependency", width="large"),
                "Doubly Material": st.column_config.TextColumn("✓ DM", width="small"),
            },
        )
    else:
        st.info("No dependencies scored.")

    st.markdown("---")
    st.markdown("### Stakeholder Assessment")
    st.caption(
        "Adjust scores to reflect your organisation's stakeholder view. "
        "These overrides update the matrix and IRO register above on re-run."
    )
    new_overrides = stakeholder_ui.render_stakeholder_panel(report)

    # Trigger rerun if overrides changed
    if new_overrides:
        current_key = _overrides_key(new_overrides)
        prev_key = st.session_state.get("_override_key", "")
        if current_key != prev_key:
            st.session_state["_override_key"] = current_key
            st.rerun()


def _collect_existing_overrides(base: DependencyReport):
    """Read stakeholder overrides stored in session state."""
    from app.models import StakeholderOverride, MaterialityScore

    overrides_state = st.session_state.get("stakeholder_overrides", {})
    stakeholder_name = st.session_state.get("stakeholder_name", "")
    _OPTION_TO_SCORE = {
        "No view": None,
        "Low": MaterialityScore.LOW,
        "Medium": MaterialityScore.MEDIUM,
        "High": MaterialityScore.HIGH,
    }

    result = []
    for dep_id, values in overrides_state.items():
        fin = _OPTION_TO_SCORE.get(values.get("financial", "No view"))
        imp = _OPTION_TO_SCORE.get(values.get("impact", "No view"))
        notes = values.get("notes", "")
        if fin is not None or imp is not None or notes:
            result.append(StakeholderOverride(
                dependency_id=dep_id,
                stakeholder_financial=fin,
                stakeholder_impact=imp,
                notes=notes,
                stakeholder_name=stakeholder_name,
            ))
    return result


def _overrides_key(overrides) -> str:
    return "|".join(
        f"{o.dependency_id}:{o.stakeholder_financial}:{o.stakeholder_impact}:{o.notes}"
        for o in sorted(overrides, key=lambda x: x.dependency_id)
    )


def render_export_row(report: AnyReport, company_name: str) -> None:
    st.markdown("---")
    st.markdown("#### Export Results")
    safe_name = company_name.replace(" ", "_").replace("/", "-")[:20]

    c1, c2, c3, c4 = st.columns(4)
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
    with c4:
        st.download_button(
            label="⬇ IRO Register",
            data=to_iro_register_csv(report),
            file_name=f"{safe_name}_iro_register.csv",
            mime="text/csv",
            use_container_width=True,
        )


def render_results(report: AnyReport) -> None:
    base = _get_base(report)
    company = base.company

    render_company_card(company, base.sasb_mapping.sasb_industry_code, base.sasb_mapping.confidence)
    render_metrics_row(base)

    st.markdown("---")
    tabs = st.tabs([
        "🌿 Natural Capital",
        "🤝 Social Capital",
        "👷 Human Capital",
        "📊 Overview",
        "⚖️ Double Materiality",
    ])

    with tabs[0]:
        render_capital_panel(base.natural_capital, "Natural Capital")
    with tabs[1]:
        render_capital_panel(base.social_capital, "Social Capital")
    with tabs[2]:
        render_capital_panel(base.human_capital, "Human Capital")
    with tabs[3]:
        render_overview_tab(report)
    with tabs[4]:
        render_double_materiality_tab(report)

    render_export_row(report, company.name)
