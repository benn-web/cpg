"""Stakeholder input panel for double materiality assessments."""
from __future__ import annotations

from typing import Union

import streamlit as st

from app.models import (
    CapitalPanel,
    DependencyReport,
    EnrichedReport,
    MaterialityScore,
    ScoredDependency,
    StakeholderOverride,
)

AnyReport = Union[DependencyReport, EnrichedReport]

_SCORE_OPTIONS = ["No view", "Low", "Medium", "High"]

_OPTION_TO_SCORE: dict[str, MaterialityScore | None] = {
    "No view": None,
    "Low": MaterialityScore.LOW,
    "Medium": MaterialityScore.MEDIUM,
    "High": MaterialityScore.HIGH,
}

_SCORE_TO_OPTION: dict[MaterialityScore, str] = {
    MaterialityScore.LOW: "Low",
    MaterialityScore.MEDIUM: "Medium",
    MaterialityScore.HIGH: "High",
    MaterialityScore.NOT_APPLICABLE: "No view",
}


def _get_base(report: AnyReport) -> DependencyReport:
    return report.base_report if isinstance(report, EnrichedReport) else report


def _all_scored_deps(base: DependencyReport) -> list[ScoredDependency]:
    deps = []
    for panel in [base.natural_capital, base.social_capital, base.human_capital]:
        deps.extend(panel.dependencies)
    return deps


def render_stakeholder_panel(report: AnyReport) -> list[StakeholderOverride]:
    """
    Render a stakeholder input form allowing users to override financial and impact
    materiality scores per dependency. Returns the current list of overrides from
    session state, applying any changes the user has made in the form.
    """
    base = _get_base(report)
    all_deps = _all_scored_deps(base)

    # Show only material dependencies (score >= medium on either dimension)
    candidate_deps = [
        d for d in all_deps
        if d.materiality_numeric >= 2 or d.impact_numeric >= 2
    ]

    if not candidate_deps:
        st.info("No material dependencies to assess. Run an analysis first.")
        return []

    # Initialise session state
    if "stakeholder_overrides" not in st.session_state:
        st.session_state.stakeholder_overrides = {}
    if "stakeholder_name" not in st.session_state:
        st.session_state.stakeholder_name = ""

    overrides: list[StakeholderOverride] = []

    with st.expander("📋 Stakeholder Assessment", expanded=False):
        st.markdown(
            "Adjust the materiality scores below to reflect your organisation's stakeholder "
            "view. These overrides are applied on top of the rule-based SASB scores and are "
            "exported in the IRO register."
        )

        stakeholder_name = st.text_input(
            "Stakeholder / group name",
            value=st.session_state.stakeholder_name,
            placeholder="e.g. Sustainability team, Board, External consultant",
            key="stakeholder_name_input",
        )
        st.session_state.stakeholder_name = stakeholder_name

        st.divider()

        for scored in candidate_deps:
            dep = scored.dependency
            dep_key = dep.id
            prev = st.session_state.stakeholder_overrides.get(dep_key, {})

            col_label, col_fin, col_imp, col_notes = st.columns([3, 1.5, 1.5, 3])

            with col_label:
                esrs = f" ({dep.esrs_topic})" if dep.esrs_topic else ""
                st.markdown(
                    f"**{dep.label}**{esrs}  \n"
                    f"<small style='color:#666'>{dep.capital_type.value.title()} · {dep.category}</small>",
                    unsafe_allow_html=True,
                )

            with col_fin:
                current_fin = _SCORE_TO_OPTION.get(scored.materiality_score, "No view")
                prev_fin = prev.get("financial", current_fin)
                sel_fin = st.selectbox(
                    "Financial",
                    _SCORE_OPTIONS,
                    index=_SCORE_OPTIONS.index(prev_fin),
                    key=f"st_fin_{dep_key}",
                    label_visibility="collapsed",
                )
                st.caption(f"Rule-based: {current_fin}")

            with col_imp:
                current_imp = _SCORE_TO_OPTION.get(scored.impact_score, "No view")
                prev_imp = prev.get("impact", current_imp)
                sel_imp = st.selectbox(
                    "Impact",
                    _SCORE_OPTIONS,
                    index=_SCORE_OPTIONS.index(prev_imp),
                    key=f"st_imp_{dep_key}",
                    label_visibility="collapsed",
                )
                st.caption(f"Rule-based: {current_imp}")

            with col_notes:
                prev_notes = prev.get("notes", "")
                notes = st.text_input(
                    "Notes",
                    value=prev_notes,
                    placeholder="Rationale for adjustment…",
                    key=f"st_notes_{dep_key}",
                    label_visibility="collapsed",
                )

            # Persist to session state
            st.session_state.stakeholder_overrides[dep_key] = {
                "financial": sel_fin,
                "impact": sel_imp,
                "notes": notes,
            }

            # Build override if either score changed from rule-based
            fin_score = _OPTION_TO_SCORE[sel_fin]
            imp_score = _OPTION_TO_SCORE[sel_imp]
            if fin_score is not None or imp_score is not None or notes:
                overrides.append(
                    StakeholderOverride(
                        dependency_id=dep_key,
                        stakeholder_financial=fin_score,
                        stakeholder_impact=imp_score,
                        notes=notes,
                        stakeholder_name=stakeholder_name,
                    )
                )

        if st.button("Reset all stakeholder inputs", type="secondary"):
            st.session_state.stakeholder_overrides = {}
            st.rerun()

    return overrides
