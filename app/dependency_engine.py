from __future__ import annotations

import json
import functools
from pathlib import Path
from typing import Optional

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

_DATA_DIR = Path(__file__).parent.parent / "data"

_SCORE_ORDER = {
    "high": 3,
    "medium": 2,
    "low": 1,
    "not_applicable": 0,
}

_GLOBAL_BASELINE: dict[str, str] = {
    # Every company has at least these regardless of sector
    "SC-003": "low",  # data privacy
    "HC-001": "low",  # employee H&S
    "NC-003": "low",  # GHG emissions
    "SC-009": "low",  # regulatory compliance
}


@functools.lru_cache(maxsize=1)
def _load_sasb_mapping() -> list[dict]:
    path = _DATA_DIR / "sasb_gics_mapping.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["mappings"]


@functools.lru_cache(maxsize=1)
def _load_dependency_data() -> dict[str, list[DependencyItem]]:
    result: dict[str, list[DependencyItem]] = {}
    for capital_type in ("natural_capital", "social_capital", "human_capital"):
        path = _DATA_DIR / f"{capital_type}.json"
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        result[capital_type] = [DependencyItem(**item) for item in raw["dependencies"]]
    return result


def resolve_sasb_industry(gics_sector: str, gics_industry: str) -> SASBIndustryMapping:
    """Map a GICS sector + industry to the best-matching SASB industry code."""
    mappings = _load_sasb_mapping()

    # Exact match on both sector and industry (pick highest confidence)
    exact: list[dict] = [
        m for m in mappings
        if m["gics_sector"].lower() == gics_sector.lower()
        and m["gics_industry"].lower() == gics_industry.lower()
    ]
    if exact:
        best = _pick_best(exact)
        return SASBIndustryMapping(**best)

    # Sector-only match — use the first (most common) industry in that sector
    sector_only: list[dict] = [
        m for m in mappings
        if m["gics_sector"].lower() == gics_sector.lower()
    ]
    if sector_only:
        best = _pick_best(sector_only)
        return SASBIndustryMapping(
            gics_sector=gics_sector,
            gics_industry=gics_industry,
            sasb_sector=best["sasb_sector"],
            sasb_industry=best["sasb_industry"],
            sasb_industry_code=best["sasb_industry_code"],
            confidence="low",
            notes=f"No exact GICS industry match; fell back to sector '{gics_sector}'",
        )

    # Unknown sector — return a generic Services mapping
    return SASBIndustryMapping(
        gics_sector=gics_sector,
        gics_industry=gics_industry,
        sasb_sector="Services",
        sasb_industry="Professional & Commercial Services",
        sasb_industry_code="SV-PS",
        confidence="low",
        notes="GICS sector not found in mapping table; global-baseline scores applied",
    )


def _pick_best(mappings: list[dict]) -> dict:
    """Return the mapping with the highest confidence; ties broken by order."""
    order = {"high": 3, "medium": 2, "low": 1}
    return max(mappings, key=lambda m: order.get(m.get("confidence", "low"), 0))


def _resolve_materiality(
    dep: DependencyItem,
    sasb_code: str,
    sasb_sector_prefix: str,
) -> tuple[MaterialityScore, str]:
    """
    Three-tier fallback:
      1. Exact SASB industry code
      2. Sector prefix match (average of available entries → max)
      3. Global baseline
    Returns (MaterialityScore, rationale_basis).
    """
    mat_map = dep.sasb_industry_materiality

    # Tier 1: exact
    if sasb_code in mat_map:
        raw = mat_map[sasb_code]
        return _parse_score(raw), f"SASB {sasb_code} (direct)"

    # Tier 2: sector prefix (e.g. "EM" matches "EM-EP", "EM-MM", ...)
    prefix_scores = [
        _SCORE_ORDER.get(v, 0)
        for k, v in mat_map.items()
        if k.startswith(sasb_sector_prefix + "-")
    ]
    if prefix_scores:
        best_num = max(prefix_scores)
        score = _num_to_score(best_num)
        return score, f"SASB sector '{sasb_sector_prefix}' (prefix match)"

    # Tier 3: global baseline
    if dep.id in _GLOBAL_BASELINE:
        raw = _GLOBAL_BASELINE[dep.id]
        return _parse_score(raw), "Global baseline"

    return MaterialityScore.NOT_APPLICABLE, "Not applicable for this sector"


def _parse_score(raw: str) -> MaterialityScore:
    mapping = {
        "high": MaterialityScore.HIGH,
        "medium": MaterialityScore.MEDIUM,
        "low": MaterialityScore.LOW,
    }
    return mapping.get(raw.lower(), MaterialityScore.NOT_APPLICABLE)


def _num_to_score(num: int) -> MaterialityScore:
    return {3: MaterialityScore.HIGH, 2: MaterialityScore.MEDIUM, 1: MaterialityScore.LOW}.get(
        num, MaterialityScore.NOT_APPLICABLE
    )


def _build_rationale(dep: DependencyItem, score: MaterialityScore, basis: str) -> str:
    level_text = {
        MaterialityScore.HIGH: "Highly material",
        MaterialityScore.MEDIUM: "Moderately material",
        MaterialityScore.LOW: "Low materiality",
        MaterialityScore.NOT_APPLICABLE: "Not applicable",
    }
    return f"{level_text[score]} per {basis}. {dep.sasb_disclosure_topic} — {dep.description[:120]}..."


def score_dependencies(company: CompanyProfile) -> DependencyReport:
    """
    Run the rule-based scoring pipeline for a company.
    Returns a DependencyReport with all three capital panels populated.
    """
    sasb_mapping = resolve_sasb_industry(company.gics_sector, company.gics_industry)
    sasb_code = sasb_mapping.sasb_industry_code
    # Sector prefix = characters before the first "-"
    sasb_prefix = sasb_code.split("-")[0] if "-" in sasb_code else sasb_code

    dep_data = _load_dependency_data()

    panels: dict[str, list[ScoredDependency]] = {
        "natural_capital": [],
        "social_capital": [],
        "human_capital": [],
    }

    for key, deps in dep_data.items():
        for dep in deps:
            score, basis = _resolve_materiality(dep, sasb_code, sasb_prefix)
            if score == MaterialityScore.NOT_APPLICABLE:
                continue
            rationale = _build_rationale(dep, score, basis)
            panels[key].append(
                ScoredDependency(
                    dependency=dep,
                    materiality_score=score,
                    materiality_numeric=MATERIALITY_NUMERIC[score],
                    rationale=rationale,
                    sasb_basis=basis,
                )
            )

    # Sort each panel: high → medium → low
    for scored_list in panels.values():
        scored_list.sort(key=lambda s: s.materiality_numeric, reverse=True)

    capital_type_map = {
        "natural_capital": CapitalType.NATURAL,
        "social_capital": CapitalType.SOCIAL,
        "human_capital": CapitalType.HUMAN,
    }

    return DependencyReport(
        company=company,
        sasb_mapping=sasb_mapping,
        natural_capital=CapitalPanel(
            capital_type=CapitalType.NATURAL,
            dependencies=panels["natural_capital"],
        ),
        social_capital=CapitalPanel(
            capital_type=CapitalType.SOCIAL,
            dependencies=panels["social_capital"],
        ),
        human_capital=CapitalPanel(
            capital_type=CapitalType.HUMAN,
            dependencies=panels["human_capital"],
        ),
    )
