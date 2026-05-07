"""Colour constants and materiality display helpers shared across UI components."""
from app.models import MaterialityScore

# Hex colours for materiality levels
COLOUR_HIGH = "#d32f2f"
COLOUR_MEDIUM = "#f57c00"
COLOUR_LOW = "#388e3c"
COLOUR_NA = "#9e9e9e"

MATERIALITY_COLOURS = {
    MaterialityScore.HIGH: COLOUR_HIGH,
    MaterialityScore.MEDIUM: COLOUR_MEDIUM,
    MaterialityScore.LOW: COLOUR_LOW,
    MaterialityScore.NOT_APPLICABLE: COLOUR_NA,
}

MATERIALITY_LABELS = {
    MaterialityScore.HIGH: "HIGH",
    MaterialityScore.MEDIUM: "MEDIUM",
    MaterialityScore.LOW: "LOW",
    MaterialityScore.NOT_APPLICABLE: "N/A",
}


def score_badge(score: MaterialityScore, llm_adjusted: bool = False) -> str:
    """Return an HTML badge string for inline display in Streamlit markdown."""
    colour = MATERIALITY_COLOURS[score]
    label = MATERIALITY_LABELS[score]
    badge = f'<span style="background:{colour};color:white;padding:2px 8px;border-radius:4px;font-size:0.8em;font-weight:bold">{label}</span>'
    if llm_adjusted:
        badge += ' <span style="color:#1565C0;font-size:0.75em">⚡ LLM adjusted</span>'
    return badge


def format_market_cap(value: float | None, currency: str = "GBP") -> str:
    if value is None:
        return "N/A"
    if value >= 1e9:
        return f"{currency} {value / 1e9:.1f}B"
    if value >= 1e6:
        return f"{currency} {value / 1e6:.0f}M"
    return f"{currency} {value:,.0f}"
