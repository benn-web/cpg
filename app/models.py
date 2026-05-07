from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field


class MaterialityScore(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NOT_APPLICABLE = "not_applicable"


MATERIALITY_NUMERIC: dict[MaterialityScore, int] = {
    MaterialityScore.HIGH: 3,
    MaterialityScore.MEDIUM: 2,
    MaterialityScore.LOW: 1,
    MaterialityScore.NOT_APPLICABLE: 0,
}


class CapitalType(str, Enum):
    NATURAL = "natural"
    SOCIAL = "social"
    HUMAN = "human"


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

class SearchResult(BaseModel):
    ticker: str
    name: str
    gics_sector: str
    match_score: float  # rapidfuzz score 0–100


class CompanyProfile(BaseModel):
    ticker: str
    name: str
    gics_sector: str
    gics_industry: str
    description: str
    market_cap: Optional[float] = None
    currency: str = "GBP"
    website: Optional[str] = None
    employees: Optional[int] = None
    country: Optional[str] = None
    raw_yfinance_data: dict = Field(default_factory=dict, exclude=True)


# ---------------------------------------------------------------------------
# SASB mapping
# ---------------------------------------------------------------------------

class SASBIndustryMapping(BaseModel):
    gics_sector: str
    gics_industry: str
    sasb_sector: str
    sasb_industry: str
    sasb_industry_code: str
    confidence: str  # "high" | "medium" | "low"
    notes: str = ""


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

class DependencyItem(BaseModel):
    id: str
    capital_type: CapitalType
    category: str
    subcategory: str
    label: str
    description: str
    tnfd_ecosystem_service: Optional[str] = None
    tnfd_pillar: Optional[str] = None
    capital_protocol_category: str
    sasb_disclosure_topic: str
    esrs_topic: Optional[str] = None
    sasb_industry_materiality: dict[str, str] = Field(default_factory=dict)
    sasb_industry_impact: dict[str, str] = Field(default_factory=dict)
    indicators: list[str] = Field(default_factory=list)


class ScoredDependency(BaseModel):
    dependency: DependencyItem
    materiality_score: MaterialityScore
    materiality_numeric: int  # 3 / 2 / 1 / 0
    impact_score: MaterialityScore = MaterialityScore.NOT_APPLICABLE
    impact_numeric: int = 0
    doubly_material: bool = False
    iro_type: str = ""  # "Impact & Risk" | "Risk" | "Impact" | "Low priority"
    rationale: str
    sasb_basis: str  # SASB code that drove the score
    llm_adjusted: bool = False
    llm_adjustment_note: Optional[str] = None


class CapitalPanel(BaseModel):
    capital_type: CapitalType
    dependencies: list[ScoredDependency]

    @property
    def high_count(self) -> int:
        return sum(1 for d in self.dependencies if d.materiality_score == MaterialityScore.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for d in self.dependencies if d.materiality_score == MaterialityScore.MEDIUM)

    @property
    def low_count(self) -> int:
        return sum(1 for d in self.dependencies if d.materiality_score == MaterialityScore.LOW)


class DependencyReport(BaseModel):
    company: CompanyProfile
    sasb_mapping: SASBIndustryMapping
    natural_capital: CapitalPanel
    social_capital: CapitalPanel
    human_capital: CapitalPanel
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    llm_enriched: bool = False
    frameworks_used: list[str] = Field(
        default_factory=lambda: [
            "TNFD v1.0",
            "SASB Standards 2023",
            "Capital Coalition Natural Capital Protocol",
            "Capital Coalition Social & Human Capital Protocol",
            "CSRD/ESRS 2024",
        ]
    )
    stakeholder_overrides: list["StakeholderOverride"] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stakeholder input
# ---------------------------------------------------------------------------

class StakeholderOverride(BaseModel):
    dependency_id: str
    stakeholder_financial: Optional[MaterialityScore] = None
    stakeholder_impact: Optional[MaterialityScore] = None
    notes: str = ""
    stakeholder_name: str = ""


# ---------------------------------------------------------------------------
# LLM enrichment
# ---------------------------------------------------------------------------

class FreetextDependency(BaseModel):
    capital_type: CapitalType
    label: str
    description: str
    materiality_score: MaterialityScore
    llm_rationale: str


class EnrichedReport(BaseModel):
    base_report: DependencyReport
    llm_additions: list[FreetextDependency] = Field(default_factory=list)
    llm_elevations: dict[str, MaterialityScore] = Field(default_factory=dict)  # id → new score
    llm_narrative: str = ""
    llm_evidence_sources: list[str] = Field(default_factory=list)
    llm_model_used: str = ""
    llm_enriched: bool = True


# ---------------------------------------------------------------------------
# Result wrapper (no exceptions leak from service layer)
# ---------------------------------------------------------------------------

T = TypeVar("T")


@dataclass
class LookupResult(Generic[T]):
    ok: bool
    data: Optional[T]
    error: Optional[str] = None

    @classmethod
    def success(cls, data: T) -> "LookupResult[T]":
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, error: str) -> "LookupResult[T]":
        return cls(ok=False, data=None, error=error)
