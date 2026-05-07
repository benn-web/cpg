from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Union

import pandas as pd

from app.models import (
    CapitalPanel,
    DependencyReport,
    EnrichedReport,
    MaterialityScore,
)

_TOOL_VERSION = "0.2.0"

AnyReport = Union[DependencyReport, EnrichedReport]

# RAG colour fills for Excel (openpyxl ARGB hex, no '#')
_FILL_HIGH = "FFD32F2F"    # red
_FILL_MEDIUM = "FFF57C00"  # amber
_FILL_LOW = "FF388E3C"     # green
_FILL_NA = "FF9E9E9E"      # grey


def _get_base_report(report: AnyReport) -> DependencyReport:
    if isinstance(report, EnrichedReport):
        return report.base_report
    return report


def flatten_report(report: AnyReport) -> pd.DataFrame:
    """Flatten a DependencyReport/EnrichedReport into a single DataFrame."""
    base = _get_base_report(report)
    rows = []

    for panel in [base.natural_capital, base.social_capital, base.human_capital]:
        for scored in panel.dependencies:
            dep = scored.dependency
            rows.append(
                {
                    "capital_type": panel.capital_type.value,
                    "category": dep.category,
                    "subcategory": dep.subcategory,
                    "dependency_id": dep.id,
                    "label": dep.label,
                    "esrs_topic": dep.esrs_topic or "",
                    "materiality_score": scored.materiality_score.value,
                    "materiality_numeric": scored.materiality_numeric,
                    "impact_score": scored.impact_score.value,
                    "impact_numeric": scored.impact_numeric,
                    "doubly_material": scored.doubly_material,
                    "iro_type": scored.iro_type,
                    "sasb_basis": scored.sasb_basis,
                    "rationale": scored.rationale,
                    "llm_adjusted": scored.llm_adjusted,
                    "llm_adjustment_note": scored.llm_adjustment_note or "",
                    "tnfd_ecosystem_service": dep.tnfd_ecosystem_service or "",
                    "sasb_disclosure_topic": dep.sasb_disclosure_topic,
                    "indicators": "; ".join(dep.indicators),
                }
            )

    # Append LLM freetext additions if present
    if isinstance(report, EnrichedReport):
        for ft in report.llm_additions:
            rows.append(
                {
                    "capital_type": ft.capital_type.value,
                    "category": "LLM Identified",
                    "subcategory": "LLM Identified",
                    "dependency_id": "LLM",
                    "label": ft.label,
                    "esrs_topic": "",
                    "materiality_score": ft.materiality_score.value,
                    "materiality_numeric": {
                        MaterialityScore.HIGH: 3,
                        MaterialityScore.MEDIUM: 2,
                        MaterialityScore.LOW: 1,
                    }.get(ft.materiality_score, 1),
                    "impact_score": "not_applicable",
                    "impact_numeric": 0,
                    "doubly_material": False,
                    "iro_type": "LLM identified",
                    "sasb_basis": "LLM analysis",
                    "rationale": ft.llm_rationale,
                    "llm_adjusted": True,
                    "llm_adjustment_note": "LLM-identified dependency",
                    "tnfd_ecosystem_service": "",
                    "sasb_disclosure_topic": "",
                    "indicators": "",
                }
            )

    return pd.DataFrame(rows)


def to_iro_register(report: AnyReport) -> pd.DataFrame:
    """
    Build a dedicated IRO (Impacts, Risks and Opportunities) register DataFrame.
    Columns follow the CSRD/ESRS double materiality assessment structure.
    """
    base = _get_base_report(report)

    rows = []
    stakeholder_map = {o.dependency_id: o for o in base.stakeholder_overrides}

    for panel in [base.natural_capital, base.social_capital, base.human_capital]:
        for scored in panel.dependencies:
            dep = scored.dependency
            override = stakeholder_map.get(dep.id)
            rows.append({
                "esrs_topic": dep.esrs_topic or "",
                "capital_type": panel.capital_type.value,
                "dependency_id": dep.id,
                "label": dep.label,
                "category": dep.category,
                "iro_type": scored.iro_type,
                "financial_materiality": scored.materiality_score.value,
                "financial_numeric": scored.materiality_numeric,
                "impact_materiality": scored.impact_score.value,
                "impact_numeric": scored.impact_numeric,
                "doubly_material": scored.doubly_material,
                "rationale": scored.rationale,
                "sasb_basis": scored.sasb_basis,
                "sasb_disclosure_topic": dep.sasb_disclosure_topic,
                "tnfd_ecosystem_service": dep.tnfd_ecosystem_service or "",
                "stakeholder_financial": override.stakeholder_financial.value if override and override.stakeholder_financial else "",
                "stakeholder_impact": override.stakeholder_impact.value if override and override.stakeholder_impact else "",
                "stakeholder_notes": override.notes if override else "",
                "stakeholder_name": override.stakeholder_name if override else "",
                "llm_adjusted": scored.llm_adjusted,
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            ["doubly_material", "financial_numeric", "impact_numeric"],
            ascending=[False, False, False],
        ).reset_index(drop=True)
    return df


def to_iro_register_csv(report: AnyReport) -> bytes:
    return to_iro_register(report).to_csv(index=False).encode("utf-8")


def _build_metadata(report: AnyReport) -> dict:
    base = _get_base_report(report)
    llm_enriched = isinstance(report, EnrichedReport) and report.llm_enriched
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool_version": _TOOL_VERSION,
        "frameworks_used": base.frameworks_used,
        "llm_enriched": llm_enriched,
        "llm_model": report.llm_model_used if isinstance(report, EnrichedReport) else None,
        "sasb_industry_code": base.sasb_mapping.sasb_industry_code,
        "sasb_confidence": base.sasb_mapping.confidence,
    }


def to_json(report: AnyReport) -> str:
    base = _get_base_report(report)
    llm_enriched = isinstance(report, EnrichedReport) and report.llm_enriched

    payload = {
        "metadata": _build_metadata(report),
        "company": base.company.model_dump(exclude={"raw_yfinance_data"}),
        "sasb_mapping": base.sasb_mapping.model_dump(),
        "dependencies": {
            "natural_capital": [
                _scored_dep_to_dict(s) for s in base.natural_capital.dependencies
            ],
            "social_capital": [
                _scored_dep_to_dict(s) for s in base.social_capital.dependencies
            ],
            "human_capital": [
                _scored_dep_to_dict(s) for s in base.human_capital.dependencies
            ],
        },
        "iro_register": to_iro_register(report).to_dict(orient="records"),
    }

    if base.stakeholder_overrides:
        payload["stakeholder_overrides"] = [
            o.model_dump() for o in base.stakeholder_overrides
        ]

    if isinstance(report, EnrichedReport) and report.llm_enriched:
        payload["llm_enrichment"] = {
            "narrative": report.llm_narrative,
            "evidence_sources": report.llm_evidence_sources,
            "llm_identified_dependencies": [
                ft.model_dump() for ft in report.llm_additions
            ],
        }

    return json.dumps(payload, indent=2, default=str)


def _scored_dep_to_dict(scored) -> dict:
    return {
        "id": scored.dependency.id,
        "label": scored.dependency.label,
        "category": scored.dependency.category,
        "subcategory": scored.dependency.subcategory,
        "esrs_topic": scored.dependency.esrs_topic,
        "materiality_score": scored.materiality_score.value,
        "materiality_numeric": scored.materiality_numeric,
        "impact_score": scored.impact_score.value,
        "impact_numeric": scored.impact_numeric,
        "doubly_material": scored.doubly_material,
        "iro_type": scored.iro_type,
        "rationale": scored.rationale,
        "llm_adjusted": scored.llm_adjusted,
        "llm_adjustment_note": scored.llm_adjustment_note,
        "sasb_disclosure_topic": scored.dependency.sasb_disclosure_topic,
        "tnfd_ecosystem_service": scored.dependency.tnfd_ecosystem_service,
        "indicators": scored.dependency.indicators,
    }


def to_csv(report: AnyReport) -> bytes:
    df = flatten_report(report)
    return df.to_csv(index=False).encode("utf-8")


def to_excel(report: AnyReport) -> bytes:
    """Export to Excel with two sheets: Capital Dependencies and IRO Register."""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.utils import get_column_letter

    dep_df = flatten_report(report)
    iro_df = to_iro_register(report)

    wb = Workbook()

    fill_map = {
        "high": PatternFill("solid", fgColor=_FILL_HIGH),
        "medium": PatternFill("solid", fgColor=_FILL_MEDIUM),
        "low": PatternFill("solid", fgColor=_FILL_LOW),
    }
    header_font = Font(bold=True)

    def _write_sheet(ws, df: pd.DataFrame, score_col: str) -> None:
        ws.append(list(df.columns))
        for cell in ws[1]:
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        mat_col_idx = list(df.columns).index(score_col) + 1

        for row_data in df.itertuples(index=False):
            ws.append(list(row_data))
            row_idx = ws.max_row
            score_cell = ws.cell(row=row_idx, column=mat_col_idx)
            fill = fill_map.get(str(score_cell.value).lower())
            if fill:
                score_cell.fill = fill

        for col_idx, col_name in enumerate(df.columns, start=1):
            col_letter = get_column_letter(col_idx)
            max_len = max(len(str(col_name)), df[col_name].astype(str).str.len().max())
            ws.column_dimensions[col_letter].width = min(max_len + 2, 50)

    ws1 = wb.active
    ws1.title = "Capital Dependencies"
    _write_sheet(ws1, dep_df, "materiality_score")

    if not iro_df.empty:
        ws2 = wb.create_sheet("IRO Register")
        _write_sheet(ws2, iro_df, "financial_materiality")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
