"""Search bar and company selector UI components."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from app.company_lookup import resolve_query, get_company_profile, _load_lse_tickers
from app.models import CompanyProfile, LookupResult, SearchResult


def render_search() -> Optional[CompanyProfile]:
    """
    Render the search UI. Returns a CompanyProfile if a company is selected,
    or None if still waiting for user input.
    """
    st.markdown("## Find an LSE Company")

    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input(
            "Company name or ticker",
            placeholder="e.g. BP or BP.L",
            key="search_input",
            label_visibility="collapsed",
        )
    with col2:
        go = st.button("Search", use_container_width=True, type="primary")

    st.caption("Enter a company name for fuzzy search, or a ticker symbol (e.g. SHEL.L)")

    # Browse by sector dropdown
    st.markdown("**— or browse FTSE All-Share —**")
    tickers = _load_lse_tickers()
    sectors = sorted(set(r["sector"] for r in tickers))
    sector_options = ["(All sectors)"] + sectors
    selected_sector = st.selectbox("Filter by sector", sector_options, key="browse_sector", label_visibility="collapsed")

    filtered = tickers if selected_sector == "(All sectors)" else [r for r in tickers if r["sector"] == selected_sector]
    browse_options = {f"{r['ticker']} — {r['name']}": r["ticker"] for r in filtered}
    selected_browse = st.selectbox(
        "Select company",
        ["(Select a company)"] + list(browse_options.keys()),
        key="browse_company",
        label_visibility="collapsed",
    )

    # Handle browse selection
    if selected_browse != "(Select a company)":
        ticker = browse_options[selected_browse]
        with st.spinner(f"Loading {ticker}..."):
            result = get_company_profile(ticker)
        if result.ok:
            return result.data
        else:
            st.error(f"Could not load {ticker}: {result.error}")
            return None

    # Handle text search
    if go and query:
        return _handle_search(query)

    return None


def _handle_search(query: str) -> Optional[CompanyProfile]:
    with st.spinner("Searching..."):
        outcome = resolve_query(query)

    # Direct ticker hit
    if isinstance(outcome, LookupResult):
        if outcome.ok:
            return outcome.data
        else:
            st.error(outcome.error)
            return None

    # Multiple fuzzy matches — let user pick
    results: list[SearchResult] = outcome
    if not results:
        st.warning("No LSE companies found matching your search. Try a ticker symbol (e.g. SHEL.L).")
        return None

    if len(results) == 1:
        with st.spinner(f"Loading {results[0].ticker}..."):
            result = get_company_profile(results[0].ticker)
        if result.ok:
            return result.data
        st.error(result.error)
        return None

    st.markdown("**Multiple matches — please select:**")
    options = {
        f"{r.ticker} — {r.name} ({r.gics_sector})": r.ticker
        for r in results
    }
    chosen_label = st.radio("", list(options.keys()), key="search_radio")
    if st.button("Analyse Selected", key="confirm_search"):
        ticker = options[chosen_label]
        with st.spinner(f"Loading {ticker}..."):
            result = get_company_profile(ticker)
        if result.ok:
            return result.data
        st.error(result.error)

    return None
