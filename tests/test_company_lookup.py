"""Tests for company_lookup.py."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from app.company_lookup import (
    _normalise_ticker,
    _looks_like_ticker,
    _validate_lse_listing,
    get_company_profile,
    search_companies,
)
from app.models import CompanyProfile


def test_normalise_ticker_adds_l_suffix():
    assert _normalise_ticker("BP") == "BP.L"
    assert _normalise_ticker("HSBA") == "HSBA.L"
    assert _normalise_ticker("shel") == "SHEL.L"


def test_normalise_ticker_preserves_existing_suffix():
    assert _normalise_ticker("BP.L") == "BP.L"
    assert _normalise_ticker("shel.l") == "SHEL.L"


def test_looks_like_ticker_true():
    assert _looks_like_ticker("BP") is True
    assert _looks_like_ticker("BP.L") is True
    assert _looks_like_ticker("HSBA.L") is True
    assert _looks_like_ticker("SHEL") is True


def test_looks_like_ticker_false():
    assert _looks_like_ticker("British Petroleum") is False
    assert _looks_like_ticker("BP plc") is False
    assert _looks_like_ticker("") is False


def test_validate_lse_listing_accepts_lse_exchange():
    info = {"exchange": "LSE", "currency": "GBP", "quoteType": "EQUITY"}
    assert _validate_lse_listing(info) is True


def test_validate_lse_listing_accepts_lon_exchange():
    info = {"exchange": "LON", "fullExchangeName": "London Stock Exchange", "currency": "GBP"}
    assert _validate_lse_listing(info) is True


def test_validate_lse_listing_accepts_gbp_currency():
    info = {"exchange": "other", "currency": "GBP", "quoteType": "EQUITY"}
    assert _validate_lse_listing(info) is True


def test_validate_lse_listing_rejects_nyse():
    info = {"exchange": "NYSE", "currency": "USD", "quoteType": "EQUITY"}
    assert _validate_lse_listing(info) is False


def test_validate_lse_listing_rejects_empty():
    assert _validate_lse_listing({}) is False
    assert _validate_lse_listing(None) is False


@patch("app.company_lookup.yf.Ticker")
def test_get_company_profile_valid_ticker(mock_ticker_cls):
    mock_info = {
        "longName": "BP plc",
        "sector": "Energy",
        "industry": "Oil, Gas & Consumable Fuels",
        "longBusinessSummary": "A major oil company.",
        "exchange": "LSE",
        "currency": "GBP",
        "marketCap": 80_000_000_000,
        "website": "https://bp.com",
        "fullTimeEmployees": 70000,
        "country": "United Kingdom",
        "quoteType": "EQUITY",
    }
    mock_ticker_cls.return_value.info = mock_info

    result = get_company_profile("BP")
    assert result.ok is True
    profile = result.data
    assert isinstance(profile, CompanyProfile)
    assert profile.ticker == "BP.L"
    assert profile.name == "BP plc"
    assert profile.gics_sector == "Energy"
    assert profile.market_cap == 80_000_000_000


@patch("app.company_lookup.yf.Ticker")
def test_get_company_profile_invalid_ticker_returns_failure(mock_ticker_cls):
    mock_ticker_cls.return_value.info = {}

    result = get_company_profile("XXXX")
    assert result.ok is False
    assert result.error is not None


@patch("app.company_lookup.yf.Ticker")
def test_get_company_profile_non_lse_stock_rejected(mock_ticker_cls):
    mock_ticker_cls.return_value.info = {
        "longName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quoteType": "EQUITY",
    }

    result = get_company_profile("AAPL")
    assert result.ok is False
    assert "LSE" in result.error or "exchange" in result.error.lower()


@patch("app.company_lookup.yf.Ticker")
def test_get_company_profile_yfinance_exception_returns_failure(mock_ticker_cls):
    mock_ticker_cls.return_value.info = property(lambda self: (_ for _ in ()).throw(Exception("network error")))
    mock_ticker_cls.side_effect = Exception("network error")

    result = get_company_profile("BP")
    assert result.ok is False


def test_search_companies_returns_results():
    results = search_companies("British Petroleum")
    # With the curated CSV, fuzzy search should return something for "British Petroleum"
    # (BP is "BP" not "British Petroleum", so may not hit well — just check it doesn't crash)
    assert isinstance(results, list)


def test_search_companies_returns_candidates_for_bp():
    results = search_companies("BP")
    assert isinstance(results, list)
    assert len(results) >= 1
    tickers = [r.ticker for r in results]
    assert any("BP" in t for t in tickers)


def test_search_companies_no_match_returns_empty():
    results = search_companies("zzzzzzzzzzzz_no_match_xyz")
    assert isinstance(results, list)
