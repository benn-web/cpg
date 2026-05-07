"""Tests for dependency_engine.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.dependency_engine import (
    _load_dependency_data,
    _load_sasb_mapping,
    _resolve_materiality,
    resolve_sasb_industry,
    score_dependencies,
)
from app.models import (
    CapitalType,
    DependencyItem,
    DependencyReport,
    MaterialityScore,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _patch_data(monkeypatch, fixtures_dir: Path):
    """Patch the data loaders to use minimal fixture files."""
    def fake_sasb():
        with open(fixtures_dir / "sasb_gics_minimal.json") as f:
            return json.load(f)["mappings"]

    def fake_deps():
        result = {}
        for key, fname in [
            ("natural_capital", "natural_capital_minimal.json"),
            ("social_capital", "social_capital_minimal.json"),
            ("human_capital", "human_capital_minimal.json"),
        ]:
            with open(fixtures_dir / fname) as f:
                raw = json.load(f)
            from app.models import DependencyItem
            result[key] = [DependencyItem(**item) for item in raw["dependencies"]]
        return result

    monkeypatch.setattr("app.dependency_engine._load_sasb_mapping", fake_sasb)
    monkeypatch.setattr("app.dependency_engine._load_dependency_data", fake_deps)
    # Clear lru_cache so patches take effect
    _load_sasb_mapping.cache_clear()
    _load_dependency_data.cache_clear()


def test_resolve_sasb_industry_exact_match(monkeypatch, fixtures_dir):
    _patch_data(monkeypatch, fixtures_dir)
    result = resolve_sasb_industry("Energy", "Oil, Gas & Consumable Fuels")
    assert result.sasb_industry_code == "EM-EP"
    assert result.confidence == "high"


def test_resolve_sasb_industry_sector_fallback(monkeypatch, fixtures_dir):
    _patch_data(monkeypatch, fixtures_dir)
    # Unknown industry in known sector
    result = resolve_sasb_industry("Energy", "Nonexistent Energy Industry")
    assert result.sasb_industry_code is not None
    assert result.confidence == "low"


def test_resolve_sasb_industry_unknown_sector(monkeypatch, fixtures_dir):
    _patch_data(monkeypatch, fixtures_dir)
    result = resolve_sasb_industry("Alien Sector", "Alien Industry")
    # Falls back to SV-PS global baseline
    assert result.sasb_industry_code == "SV-PS"
    assert result.confidence == "low"


def test_resolve_materiality_exact_match():
    dep = DependencyItem(
        id="NC-001",
        capital_type=CapitalType.NATURAL,
        category="Water",
        subcategory="Water Quantity",
        label="Water",
        description="test",
        capital_protocol_category="Natural Capital",
        sasb_disclosure_topic="Water Management",
        sasb_industry_materiality={"EM-EP": "high", "FN-CB": "low"},
    )
    score, basis = _resolve_materiality(dep, "EM-EP", "EM")
    assert score == MaterialityScore.HIGH
    assert "EM-EP" in basis


def test_resolve_materiality_sector_prefix_fallback():
    dep = DependencyItem(
        id="NC-001",
        capital_type=CapitalType.NATURAL,
        category="Water",
        subcategory="Water Quantity",
        label="Water",
        description="test",
        capital_protocol_category="Natural Capital",
        sasb_disclosure_topic="Water Management",
        sasb_industry_materiality={"EM-EP": "high", "EM-MM": "medium"},
    )
    # No exact "EM-NM" match, but sector prefix "EM" has entries
    score, basis = _resolve_materiality(dep, "EM-NM", "EM")
    assert score == MaterialityScore.HIGH  # max of high/medium = high
    assert "prefix" in basis.lower()


def test_resolve_materiality_not_applicable():
    dep = DependencyItem(
        id="NC-007",
        capital_type=CapitalType.NATURAL,
        category="Biodiversity",
        subcategory="Ecosystem Integrity",
        label="Biodiversity",
        description="test",
        capital_protocol_category="Natural Capital",
        sasb_disclosure_topic="Biodiversity",
        sasb_industry_materiality={"EM-MM": "high"},
    )
    # SV-ME has no match in materiality map and no sector prefix entries
    score, basis = _resolve_materiality(dep, "SV-ME", "SV")
    assert score == MaterialityScore.NOT_APPLICABLE


def test_score_dependencies_returns_three_panels(monkeypatch, fixtures_dir, sample_company):
    _patch_data(monkeypatch, fixtures_dir)
    report = score_dependencies(sample_company)
    assert isinstance(report, DependencyReport)
    assert report.natural_capital is not None
    assert report.social_capital is not None
    assert report.human_capital is not None


def test_score_dependencies_high_materiality_for_oil_gas(monkeypatch, fixtures_dir, sample_company):
    _patch_data(monkeypatch, fixtures_dir)
    report = score_dependencies(sample_company)
    # NC-001 (water) should be HIGH for EM-EP
    water_deps = [
        d for d in report.natural_capital.dependencies
        if d.dependency.id == "NC-001"
    ]
    assert len(water_deps) == 1
    assert water_deps[0].materiality_score == MaterialityScore.HIGH


def test_score_dependencies_sorted_high_first(monkeypatch, fixtures_dir, sample_company):
    _patch_data(monkeypatch, fixtures_dir)
    report = score_dependencies(sample_company)
    scores = [d.materiality_numeric for d in report.natural_capital.dependencies]
    assert scores == sorted(scores, reverse=True)


def test_score_dependencies_excludes_not_applicable(monkeypatch, fixtures_dir, sample_company):
    _patch_data(monkeypatch, fixtures_dir)
    report = score_dependencies(sample_company)
    all_deps = (
        report.natural_capital.dependencies
        + report.social_capital.dependencies
        + report.human_capital.dependencies
    )
    for scored in all_deps:
        assert scored.materiality_score != MaterialityScore.NOT_APPLICABLE


def test_score_dependencies_banking_sector(monkeypatch, fixtures_dir):
    _patch_data(monkeypatch, fixtures_dir)
    from app.models import CompanyProfile
    bank = CompanyProfile(
        ticker="LLOY.L",
        name="Lloyds Banking Group",
        gics_sector="Financials",
        gics_industry="Banks",
        description="A major UK retail bank.",
    )
    report = score_dependencies(bank)
    # SC-003 (data privacy) should be HIGH for FN-CB
    privacy_deps = [
        d for d in report.social_capital.dependencies
        if d.dependency.id == "SC-003"
    ]
    assert len(privacy_deps) == 1
    assert privacy_deps[0].materiality_score == MaterialityScore.HIGH


def test_dependency_data_cached(monkeypatch, fixtures_dir):
    _patch_data(monkeypatch, fixtures_dir)
    result1 = _load_dependency_data()
    result2 = _load_dependency_data()
    assert result1 is result2  # same object from lru_cache
