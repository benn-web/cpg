from __future__ import annotations

import json
import logging
import time
from typing import Optional

import anthropic

from app.models import (
    CapitalType,
    CompanyProfile,
    DependencyReport,
    EnrichedReport,
    FreetextDependency,
    MaterialityScore,
)

logger = logging.getLogger(__name__)

_LLM_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "confirmed_dependencies": {
            "type": "array",
            "items": {"type": "string"},
            "description": "IDs of rule-based dependencies you agree are material",
        },
        "elevated_dependencies": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": "Map of dependency ID to revised materiality ('high'|'medium'|'low')",
        },
        "new_dependencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "capital_type": {"type": "string"},
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                    "materiality_score": {"type": "string"},
                    "llm_rationale": {"type": "string"},
                },
                "required": ["capital_type", "label", "description", "materiality_score", "llm_rationale"],
            },
        },
        "narrative": {
            "type": "string",
            "description": "Company-specific capital dependency narrative (max 300 words)",
        },
        "evidence_sources": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Publicly known reports or disclosures cited as evidence",
        },
    },
    "required": ["confirmed_dependencies", "elevated_dependencies", "new_dependencies", "narrative", "evidence_sources"],
}


def _build_system_prompt() -> str:
    return (
        "You are an expert ESG analyst specialising in the TNFD v1.0 framework, "
        "SASB Standards, and the Capital Coalition's Natural, Social & Human Capital Protocols. "
        "You assess capital dependency materiality for publicly listed companies. "
        "Be precise, evidence-based, and cite specific company disclosures or public reports where possible."
    )


def _build_user_prompt(company: CompanyProfile, base_report: DependencyReport) -> str:
    # Summarise rule-based dependencies concisely
    def summarise_panel(panel_name: str, panel) -> str:
        lines = [f"\n### {panel_name}"]
        for dep in panel.dependencies:
            lines.append(
                f"- [{dep.dependency.id}] {dep.dependency.label} "
                f"({dep.materiality_score.value}): {dep.dependency.description[:80]}..."
            )
        return "\n".join(lines)

    nat = summarise_panel("Natural Capital", base_report.natural_capital)
    soc = summarise_panel("Social Capital", base_report.social_capital)
    hum = summarise_panel("Human Capital", base_report.human_capital)

    schema_str = json.dumps(_LLM_RESPONSE_SCHEMA, indent=2)

    return f"""
## Company Profile
- **Name**: {company.name}
- **Ticker**: {company.ticker}
- **GICS Sector**: {company.gics_sector}
- **GICS Industry**: {company.gics_industry}
- **Employees**: {company.employees or 'Unknown'}
- **Country**: {company.country or 'Unknown'}
- **Description**: {company.description[:400] if company.description else 'Not available'}

## SASB Classification
- **Industry**: {base_report.sasb_mapping.sasb_industry} ({base_report.sasb_mapping.sasb_industry_code})
- **Confidence**: {base_report.sasb_mapping.confidence}

## Rule-Based Dependency Assessment
{nat}
{soc}
{hum}

## Your Task
Review the rule-based assessment above and provide a company-specific enrichment. Consider:
1. Are there company-specific factors that make any dependency more or less material than the sector average?
2. Are there material dependencies not captured by the sector-level rules (e.g., specific supply chain exposures, recent controversies, transition commitments)?
3. What does publicly available information (annual reports, sustainability reports, ESG ratings) reveal about this company's actual dependency profile?

Return ONLY valid JSON matching this exact schema. No markdown fences, no explanatory text:
{schema_str}
""".strip()


def _parse_llm_response(
    raw: str,
    base_report: DependencyReport,
    model_used: str,
) -> EnrichedReport:
    """Parse the LLM JSON response and merge into an EnrichedReport."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("LLM returned invalid JSON: %s", exc)
        raise

    # Apply score elevations
    elevated: dict[str, MaterialityScore] = {}
    for dep_id, new_score_str in data.get("elevated_dependencies", {}).items():
        try:
            elevated[dep_id] = MaterialityScore(new_score_str.lower())
        except ValueError:
            pass

    # Update ScoredDependency objects in place (create new list)
    def apply_elevations(panel):
        updated = []
        for scored in panel.dependencies:
            if scored.dependency.id in elevated:
                new_score = elevated[scored.dependency.id]
                from app.models import MATERIALITY_NUMERIC
                updated.append(
                    scored.model_copy(
                        update={
                            "materiality_score": new_score,
                            "materiality_numeric": MATERIALITY_NUMERIC[new_score],
                            "llm_adjusted": True,
                            "llm_adjustment_note": f"LLM raised to {new_score.value}",
                        }
                    )
                )
            else:
                updated.append(scored)
        return panel.model_copy(update={"dependencies": sorted(updated, key=lambda s: s.materiality_numeric, reverse=True)})

    enriched_nat = apply_elevations(base_report.natural_capital)
    enriched_soc = apply_elevations(base_report.social_capital)
    enriched_hum = apply_elevations(base_report.human_capital)

    updated_base = base_report.model_copy(
        update={
            "natural_capital": enriched_nat,
            "social_capital": enriched_soc,
            "human_capital": enriched_hum,
            "llm_enriched": True,
        }
    )

    # Parse new freetext dependencies
    additions: list[FreetextDependency] = []
    for item in data.get("new_dependencies", []):
        try:
            ct = CapitalType(item.get("capital_type", "").lower())
            ms = MaterialityScore(item.get("materiality_score", "low").lower())
            additions.append(
                FreetextDependency(
                    capital_type=ct,
                    label=item["label"],
                    description=item.get("description", ""),
                    materiality_score=ms,
                    llm_rationale=item.get("llm_rationale", ""),
                )
            )
        except (ValueError, KeyError) as exc:
            logger.debug("Skipping malformed new_dependency: %s", exc)

    return EnrichedReport(
        base_report=updated_base,
        llm_additions=additions,
        llm_elevations=elevated,
        llm_narrative=data.get("narrative", ""),
        llm_evidence_sources=data.get("evidence_sources", []),
        llm_model_used=model_used,
    )


def enrich_dependencies(
    company: CompanyProfile,
    base_report: DependencyReport,
    api_key: str,
    model: str = "claude-opus-4-5",
    max_tokens: int = 2000,
    max_retries: int = 3,
) -> EnrichedReport:
    """
    Call Claude to enrich the rule-based dependency report with company-specific analysis.
    Falls back to returning the base_report (as an EnrichedReport wrapper) on failure.
    """
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(company, base_report)

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw_text = response.content[0].text
            return _parse_llm_response(raw_text, base_report, model)

        except anthropic.RateLimitError as exc:
            wait = 2 ** attempt
            logger.warning("Rate limit hit (attempt %d/%d), waiting %ds", attempt + 1, max_retries, wait)
            last_error = exc
            time.sleep(wait)

        except anthropic.APIStatusError as exc:
            logger.error("Anthropic API error: %s", exc)
            last_error = exc
            break

        except (json.JSONDecodeError, Exception) as exc:
            logger.error("LLM enrichment parse error: %s", exc)
            last_error = exc
            break

    logger.warning("LLM enrichment failed after %d attempts: %s", max_retries, last_error)
    # Return base report wrapped in EnrichedReport with empty enrichments
    return EnrichedReport(
        base_report=base_report,
        llm_narrative="",
        llm_enriched=False,
        llm_model_used=model,
    )
