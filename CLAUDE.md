# CPG Capital Dependencies Tool

## Purpose
Identifies natural, social, and human capital dependencies for any LSE-listed firm.
Maps GICS sector/industry (via yfinance) to SASB materiality ratings, supplemented
optionally by Claude API enrichment. Built on TNFD v1.0, SASB Standards, and
Capital Coalition Protocols.

## Run
```bash
streamlit run app/main.py
```

## Test
```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing
```

## Architecture
```
User Input
  → app/company_lookup.py   (yfinance + rapidfuzz against data/lse_tickers.csv)
  → app/dependency_engine.py (GICS → SASB → materiality scoring from JSON knowledge base)
  → app/llm_enrichment.py   (optional Claude enrichment)
  → app/ui/                 (Streamlit dashboard)
  → app/export.py           (JSON / CSV / Excel)
```

## Key design notes
- **SASB codes are the join key** between yfinance GICS classification and dependency materiality.
  `data/sasb_gics_mapping.json` maps GICS sector+industry → SASB industry code.
- **Knowledge base** lives in `data/natural_capital.json`, `data/social_capital.json`,
  `data/human_capital.json`. Each dependency carries a `sasb_industry_materiality` map
  (SASB code → high/medium/low). Edit these files to add coverage or update ratings.
- **LSE ticker list** (`data/lse_tickers.csv`) covers FTSE All-Share. Format: `ticker,name,sector,index`.
  Refresh periodically from the LSE website. Used for fuzzy name search only — yfinance
  search is not filtered to LSE.
- **LLM enrichment** is off by default. Enable via sidebar toggle or `LLM_ENRICHMENT_ENABLED=true`
  in `.env`. Set `ANTHROPIC_API_KEY` to use it.

## Adding new sectors
1. Add entries to `data/sasb_gics_mapping.json`
2. Add `sasb_industry_materiality` entries to the relevant capital JSON files

## Environment variables
| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required for LLM enrichment |
| `LLM_ENRICHMENT_ENABLED` | `false` | Pre-enable LLM toggle |
| `LLM_MODEL` | `claude-opus-4-5` | Claude model to use |
| `MAX_TOKENS` | `2000` | Max tokens for LLM response |
