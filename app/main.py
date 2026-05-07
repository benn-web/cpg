"""Streamlit entry point for the Capital Dependencies Assessment Tool."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

import streamlit as st
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from app.dependency_engine import score_dependencies
from app.llm_enrichment import enrich_dependencies
from app.models import CompanyProfile, DependencyReport, EnrichedReport
from app.ui import results as results_ui
from app.ui import search as search_ui

_APP_VERSION = "0.1.0"


def _init_session_state() -> None:
    st.session_state.setdefault("company", None)
    st.session_state.setdefault("report", None)
    st.session_state.setdefault("llm_error", None)


def _render_sidebar() -> tuple[bool, str]:
    """Render sidebar controls. Returns (llm_enabled, api_key)."""
    with st.sidebar:
        st.markdown(f"## Capital Dependencies\n*v{_APP_VERSION}*")
        st.divider()

        st.markdown("### Settings")
        llm_default = os.getenv("LLM_ENRICHMENT_ENABLED", "false").lower() == "true"
        llm_enabled = st.toggle("Enable Claude Analysis", value=llm_default, help="Enriches rule-based results with company-specific LLM analysis using Claude.")

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if llm_enabled and not api_key:
            api_key = st.text_input(
                "Anthropic API Key",
                type="password",
                placeholder="sk-ant-...",
                help="Required for LLM enrichment. Set ANTHROPIC_API_KEY in .env to avoid entering it here.",
            )

        st.divider()
        st.markdown("### Frameworks")
        st.markdown(
            "- **TNFD v1.0** — Nature dependencies\n"
            "- **SASB 2023** — Sector materiality\n"
            "- **Capital Coalition Protocols** — Dependency taxonomy"
        )

        st.divider()
        with st.expander("About", expanded=False):
            st.markdown(
                "This tool identifies material natural, social, and human capital "
                "dependencies for any LSE-listed firm based on its GICS sector "
                "classification and established sustainability frameworks.\n\n"
                "Rule-based scoring maps your company's GICS industry to SASB "
                "materiality ratings. Optional Claude analysis adds company-specific "
                "nuance from public disclosures."
            )

        if st.button("Reset / New Search", use_container_width=True):
            st.session_state.company = None
            st.session_state.report = None
            st.session_state.llm_error = None
            st.rerun()

    return llm_enabled, api_key


def _run_analysis(
    company: CompanyProfile,
    llm_enabled: bool,
    api_key: str,
) -> Union[DependencyReport, EnrichedReport]:
    with st.spinner("Running capital dependency assessment..."):
        report = score_dependencies(company)

    if llm_enabled and api_key:
        model = os.getenv("LLM_MODEL", "claude-opus-4-5")
        max_tokens = int(os.getenv("MAX_TOKENS", "2000"))
        with st.spinner("Enriching with Claude analysis..."):
            enriched = enrich_dependencies(
                company=company,
                base_report=report,
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
            )
        if not enriched.llm_enriched:
            st.warning(
                "Claude enrichment failed or returned invalid output. "
                "Showing rule-based results only.",
                icon="⚠️",
            )
        return enriched
    elif llm_enabled and not api_key:
        st.warning("LLM enrichment enabled but no API key provided. Showing rule-based results.", icon="⚠️")

    return report


def main() -> None:
    st.set_page_config(
        page_title="Capital Dependencies | LSE",
        page_icon="🌿",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _init_session_state()
    llm_enabled, api_key = _render_sidebar()

    # If we have a cached report, show results
    if st.session_state.report is not None and st.session_state.company is not None:
        results_ui.render_results(st.session_state.report)
        return

    # If we have a company but no report yet, run analysis
    if st.session_state.company is not None:
        company: CompanyProfile = st.session_state.company
        st.session_state.report = _run_analysis(company, llm_enabled, api_key)
        st.rerun()

    # Phase 1: Show search UI
    st.title("Capital Dependencies Assessment")
    st.markdown(
        "Identify the **natural, social, and human capital** dependencies material to any "
        "London Stock Exchange–listed firm, mapped to TNFD, SASB, and Capital Coalition frameworks."
    )
    st.divider()

    company = search_ui.render_search()
    if company is not None:
        st.session_state.company = company
        st.rerun()


if __name__ == "__main__":
    main()
