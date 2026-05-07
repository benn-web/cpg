"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.models import (
    CapitalPanel,
    CapitalType,
    CompanyProfile,
    DependencyItem,
    DependencyReport,
    MaterialityScore,
    MATERIALITY_NUMERIC,
    SASBIndustryMapping,
    ScoredDependency,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_company() -> CompanyProfile:
    return CompanyProfile(
        ticker="BP.L",
        name="BP plc",
        gics_sector="Energy",
        gics_industry="Oil, Gas & Consumable Fuels",
        description="BP p.l.c. is a British multinational oil and gas company.",
        market_cap=82_000_000_000,
        currency="GBP",
        website="https://www.bp.com",
        employees=70000,
        country="United Kingdom",
    )


@pytest.fixture
def sample_sasb_mapping() -> SASBIndustryMapping:
    return SASBIndustryMapping(
        gics_sector="Energy",
        gics_industry="Oil, Gas & Consumable Fuels",
        sasb_sector="Extractives & Minerals Processing",
        sasb_industry="Oil & Gas – Exploration & Production",
        sasb_industry_code="EM-EP",
        confidence="high",
    )


@pytest.fixture
def sample_scored_dep() -> ScoredDependency:
    dep = DependencyItem(
        id="NC-001",
        capital_type=CapitalType.NATURAL,
        category="Water",
        subcategory="Water Quantity",
        label="Water Withdrawal & Consumption",
        description="Operational reliance on freshwater supplies.",
        capital_protocol_category="Natural Capital",
        sasb_disclosure_topic="Water Management",
        sasb_industry_materiality={"EM-EP": "high"},
        indicators=["Total water withdrawn (m³/year)"],
    )
    return ScoredDependency(
        dependency=dep,
        materiality_score=MaterialityScore.HIGH,
        materiality_numeric=3,
        rationale="Highly material per SASB EM-EP (direct).",
        sasb_basis="SASB EM-EP (direct)",
    )


@pytest.fixture
def sample_report(sample_company, sample_sasb_mapping, sample_scored_dep) -> DependencyReport:
    sc_dep = DependencyItem(
        id="SC-001",
        capital_type=CapitalType.SOCIAL,
        category="Community Relations",
        subcategory="Social License to Operate",
        label="Community Relations & Social License",
        description="Dependency on maintaining community trust.",
        capital_protocol_category="Social Capital",
        sasb_disclosure_topic="Community Relations",
        sasb_industry_materiality={"EM-EP": "high"},
        indicators=["Number of community complaints"],
    )
    sc_scored = ScoredDependency(
        dependency=sc_dep,
        materiality_score=MaterialityScore.HIGH,
        materiality_numeric=3,
        rationale="Highly material per SASB EM-EP (direct).",
        sasb_basis="SASB EM-EP (direct)",
    )

    hc_dep = DependencyItem(
        id="HC-001",
        capital_type=CapitalType.HUMAN,
        category="Health & Safety",
        subcategory="Employee Health & Safety",
        label="Employee Health & Safety",
        description="Dependency on workforce safety.",
        capital_protocol_category="Human Capital",
        sasb_disclosure_topic="Employee Health & Safety",
        sasb_industry_materiality={"EM-EP": "high"},
        indicators=["TRIR"],
    )
    hc_scored = ScoredDependency(
        dependency=hc_dep,
        materiality_score=MaterialityScore.MEDIUM,
        materiality_numeric=2,
        rationale="Moderately material per SASB EM-EP (direct).",
        sasb_basis="SASB EM-EP (direct)",
    )

    return DependencyReport(
        company=sample_company,
        sasb_mapping=sample_sasb_mapping,
        natural_capital=CapitalPanel(
            capital_type=CapitalType.NATURAL,
            dependencies=[sample_scored_dep],
        ),
        social_capital=CapitalPanel(
            capital_type=CapitalType.SOCIAL,
            dependencies=[sc_scored],
        ),
        human_capital=CapitalPanel(
            capital_type=CapitalType.HUMAN,
            dependencies=[hc_scored],
        ),
    )
