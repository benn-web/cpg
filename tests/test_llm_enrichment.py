"""Tests for llm_enrichment.py."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.llm_enrichment import enrich_dependencies
from app.models import EnrichedReport, MaterialityScore


def _make_valid_llm_response(elevated_ids=None, new_deps=None) -> str:
    return json.dumps(
        {
            "confirmed_dependencies": ["NC-001", "SC-001"],
            "elevated_dependencies": elevated_ids or {},
            "new_dependencies": new_deps or [],
            "narrative": "BP plc has significant water and climate risk exposure due to its upstream oil operations.",
            "evidence_sources": ["BP Annual Report 2023", "BP Sustainability Report 2023"],
        }
    )


@patch("app.llm_enrichment.anthropic.Anthropic")
def test_enrich_dependencies_valid_response(mock_anthropic_cls, sample_company, sample_report):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=_make_valid_llm_response())]
    mock_client.messages.create.return_value = mock_response

    result = enrich_dependencies(
        company=sample_company,
        base_report=sample_report,
        api_key="test-key",
    )

    assert isinstance(result, EnrichedReport)
    assert result.llm_narrative != ""
    assert len(result.llm_evidence_sources) > 0
    assert result.llm_enriched is True


@patch("app.llm_enrichment.anthropic.Anthropic")
def test_enrich_dependencies_with_elevation(mock_anthropic_cls, sample_company, sample_report):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    # Elevate HC-001 from medium to high
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=_make_valid_llm_response(elevated_ids={"HC-001": "high"}))]
    mock_client.messages.create.return_value = mock_response

    result = enrich_dependencies(
        company=sample_company,
        base_report=sample_report,
        api_key="test-key",
    )

    assert "HC-001" in result.llm_elevations
    # Find HC-001 in the human capital panel
    hc_deps = result.base_report.human_capital.dependencies
    hc_001 = next((d for d in hc_deps if d.dependency.id == "HC-001"), None)
    if hc_001:
        assert hc_001.llm_adjusted is True
        assert hc_001.materiality_score == MaterialityScore.HIGH


@patch("app.llm_enrichment.anthropic.Anthropic")
def test_enrich_dependencies_invalid_json_returns_base(mock_anthropic_cls, sample_company, sample_report):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="this is not valid json at all")]
    mock_client.messages.create.return_value = mock_response

    result = enrich_dependencies(
        company=sample_company,
        base_report=sample_report,
        api_key="test-key",
    )

    assert isinstance(result, EnrichedReport)
    assert result.llm_enriched is False
    assert result.llm_narrative == ""


@patch("app.llm_enrichment.anthropic.Anthropic")
def test_enrich_dependencies_rate_limit_retries(mock_anthropic_cls, sample_company, sample_report):
    import anthropic as _anthropic

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    success_response = MagicMock()
    success_response.content = [MagicMock(text=_make_valid_llm_response())]

    mock_client.messages.create.side_effect = [
        _anthropic.RateLimitError("rate limited", response=MagicMock(), body={}),
        success_response,
    ]

    with patch("app.llm_enrichment.time.sleep"):  # skip actual sleep
        result = enrich_dependencies(
            company=sample_company,
            base_report=sample_report,
            api_key="test-key",
            max_retries=3,
        )

    assert mock_client.messages.create.call_count == 2
    assert isinstance(result, EnrichedReport)


@patch("app.llm_enrichment.anthropic.Anthropic")
def test_enrich_dependencies_api_error_graceful_failure(mock_anthropic_cls, sample_company, sample_report):
    import anthropic as _anthropic

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    mock_client.messages.create.side_effect = _anthropic.APIStatusError(
        "server error", response=MagicMock(status_code=500), body={}
    )

    result = enrich_dependencies(
        company=sample_company,
        base_report=sample_report,
        api_key="test-key",
    )

    assert isinstance(result, EnrichedReport)
    assert result.llm_enriched is False
