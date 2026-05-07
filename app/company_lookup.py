from __future__ import annotations

import re
import csv
import functools
from pathlib import Path
from typing import Optional

import yfinance as yf
from rapidfuzz import process, fuzz

from app.models import CompanyProfile, LookupResult, SearchResult

_DATA_DIR = Path(__file__).parent.parent / "data"
_TICKER_CSV = _DATA_DIR / "lse_tickers.csv"

# yfinance exchange identifiers that indicate LSE listing
_LSE_EXCHANGES = {"LSE", "LON", "London Stock Exchange"}

_TICKER_RE = re.compile(r"^[A-Z0-9]{1,6}(\.L)?$", re.IGNORECASE)


@functools.lru_cache(maxsize=1)
def _load_lse_tickers() -> list[dict]:
    """Load the curated LSE ticker list from CSV (cached after first call)."""
    rows = []
    with open(_TICKER_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _normalise_ticker(ticker: str) -> str:
    """Ensure ticker has .L suffix for LSE."""
    ticker = ticker.strip().upper()
    if not ticker.endswith(".L"):
        ticker += ".L"
    return ticker


def _looks_like_ticker(query: str) -> bool:
    return bool(_TICKER_RE.match(query.strip()))


def _validate_lse_listing(info: dict) -> bool:
    """Return True if yfinance info dict appears to be an LSE-listed stock."""
    if not info:
        return False
    exchange = info.get("exchange", "") or ""
    full_exchange = info.get("fullExchangeName", "") or ""
    currency = info.get("currency", "") or ""
    # Accept GBP or GBp-denominated stocks, or explicit LSE exchange tags
    return (
        any(tag in (exchange + " " + full_exchange).upper() for tag in ("LSE", "LON", "LONDON"))
        or currency in ("GBP", "GBp", "GBX")
    )


def search_companies(query: str) -> list[SearchResult]:
    """
    Fuzzy-search the curated LSE ticker list by company name or ticker.
    Returns up to 5 ranked candidates.
    """
    tickers = _load_lse_tickers()
    # Build search corpus: "ticker — name"
    corpus = [f"{r['ticker']} — {r['name']}" for r in tickers]

    matches = process.extract(
        query,
        corpus,
        scorer=fuzz.WRatio,
        limit=5,
        score_cutoff=40,
    )
    results = []
    for match_str, score, idx in matches:
        row = tickers[idx]
        results.append(
            SearchResult(
                ticker=row["ticker"],
                name=row["name"],
                gics_sector=row["sector"],
                match_score=score,
            )
        )
    return results


def get_company_profile(ticker: str) -> LookupResult[CompanyProfile]:
    """
    Fetch company profile from yfinance for a given LSE ticker.
    Normalises ticker to .L suffix and validates exchange.
    """
    norm = _normalise_ticker(ticker)
    try:
        yt = yf.Ticker(norm)
        info = yt.info or {}
    except Exception as exc:
        return LookupResult.failure(f"yfinance error for {norm}: {exc}")

    if not info or info.get("quoteType") is None:
        return LookupResult.failure(
            f"No data returned for '{norm}'. The ticker may be delisted or invalid."
        )

    if not _validate_lse_listing(info):
        exchange = info.get("exchange", "unknown")
        return LookupResult.failure(
            f"'{norm}' does not appear to be an LSE-listed stock "
            f"(exchange: {exchange}). Ensure you are using the correct ticker with .L suffix."
        )

    profile = CompanyProfile(
        ticker=norm,
        name=info.get("longName") or info.get("shortName") or norm,
        gics_sector=info.get("sector") or "Unknown",
        gics_industry=info.get("industry") or "Unknown",
        description=info.get("longBusinessSummary") or "",
        market_cap=info.get("marketCap"),
        currency=info.get("currency", "GBP"),
        website=info.get("website"),
        employees=info.get("fullTimeEmployees"),
        country=info.get("country"),
        raw_yfinance_data=info,
    )
    return LookupResult.success(profile)


def resolve_query(query: str) -> LookupResult[CompanyProfile] | list[SearchResult]:
    """
    Entry point for the UI search bar.
    - If query looks like a ticker → attempt direct lookup
    - Otherwise → return fuzzy search results for the user to pick from
    """
    query = query.strip()
    if not query:
        return LookupResult.failure("Please enter a company name or ticker symbol.")

    if _looks_like_ticker(query):
        return get_company_profile(query)

    return search_companies(query)
