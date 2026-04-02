"""Shared theme constants and CSS injection for Prometheus Streamlit dashboard."""

from __future__ import annotations

import streamlit as st

# ── Color palette ─────────────────────────────────────────

BG = "#0d1117"
BG_SECONDARY = "#161b22"
BORDER = "#30363d"
TEXT = "#c9d1d9"
TEXT_MUTED = "#8b949e"
ACCENT = "#58a6ff"

# Signal colors
BULL = "#3fb950"      # green  — win / bullish
BEAR = "#f85149"      # red    — loss / bearish
WARN = "#d29922"      # yellow — warning / neutral
NEUTRAL = "#8b949e"   # muted  — neutral/hold

# Consensus verdict colors
VERDICT_COLORS = {
    "strong_buy":   "#238636",   # deep green
    "buy":          "#3fb950",   # green
    "neutral":      "#d29922",   # yellow
    "sell":         "#da3633",   # red
    "strong_sell":  "#b91c1c",   # deep red
}

VERDICT_LABELS = {
    "strong_buy":   "STRONG BUY",
    "buy":          "BUY",
    "neutral":      "NEUTRAL",
    "sell":         "SELL",
    "strong_sell":  "STRONG SELL",
}

# Stance colors for agent opinions
STANCE_COLORS = {
    "strongly_bullish":  "#238636",
    "bullish":           "#3fb950",
    "slightly_bullish":  "#56d364",
    "neutral":           "#d29922",
    "slightly_bearish":  "#f0883e",
    "bearish":           "#f85149",
    "strongly_bearish":  "#b91c1c",
}

# Alert severity colors
SEVERITY_COLORS = {
    "critical": "#f85149",
    "high":     "#d29922",
    "medium":   "#58a6ff",
    "low":      "#8b949e",
    "info":     "#8b949e",
}

# Agent display metadata (name -> emoji)
AGENT_EMOJIS = {
    "bull":        "🐂",
    "bear":        "🐻",
    "indicator":   "📊",
    "risk":        "⚖️",
    "sentiment":   "📡",
    "political":   "🏛️",
    "contrarian":  "🔄",
}

AGENT_DISPLAY = {
    "bull":        "Bull Agent",
    "bear":        "Bear Agent",
    "indicator":   "Indicator Agent",
    "risk":        "Risk Agent",
    "sentiment":   "Sentiment Agent",
    "political":   "Political Agent",
    "contrarian":  "Contrarian Agent",
}


# ── CSS ───────────────────────────────────────────────────

def inject_custom_css() -> None:
    """Inject custom CSS via st.markdown for consistent dark styling."""
    st.markdown(
        f"""
        <style>
        /* ── Global resets ── */
        .stApp {{
            background-color: {BG};
        }}

        /* ── Metric cards ── */
        div[data-testid="metric-container"] {{
            background-color: {BG_SECONDARY};
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 16px 20px;
        }}
        div[data-testid="metric-container"] label {{
            color: {TEXT_MUTED} !important;
            font-size: 0.75rem !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        div[data-testid="metric-container"] [data-testid="stMetricValue"] {{
            color: {TEXT} !important;
            font-size: 1.75rem !important;
            font-weight: 700;
        }}

        /* ── Cards ── */
        .prom-card {{
            background-color: {BG_SECONDARY};
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
        }}

        .prom-card-title {{
            color: {ACCENT};
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 4px;
        }}

        /* ── Agent cards ── */
        .agent-card {{
            background-color: {BG_SECONDARY};
            border-radius: 8px;
            padding: 14px;
            margin-bottom: 10px;
            border-left: 4px solid {BORDER};
        }}

        .agent-card.bullish  {{ border-left-color: {BULL}; }}
        .agent-card.bearish  {{ border-left-color: {BEAR}; }}
        .agent-card.neutral  {{ border-left-color: {WARN}; }}

        .agent-name {{
            font-size: 0.9rem;
            font-weight: 700;
            color: {TEXT};
        }}

        .agent-stance {{
            font-size: 0.75rem;
            color: {TEXT_MUTED};
            margin-top: 2px;
        }}

        /* ── Verdict badge ── */
        .verdict-badge {{
            display: inline-block;
            padding: 6px 18px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 1.1rem;
            letter-spacing: 0.08em;
            margin: 8px 0;
        }}

        /* ── Severity badges ── */
        .badge-critical {{ background: {SEVERITY_COLORS["critical"]}22; color: {SEVERITY_COLORS["critical"]}; border: 1px solid {SEVERITY_COLORS["critical"]}55; border-radius: 4px; padding: 2px 8px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }}
        .badge-high     {{ background: {SEVERITY_COLORS["high"]}22;     color: {SEVERITY_COLORS["high"]};     border: 1px solid {SEVERITY_COLORS["high"]}55;     border-radius: 4px; padding: 2px 8px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }}
        .badge-medium   {{ background: {SEVERITY_COLORS["medium"]}22;   color: {SEVERITY_COLORS["medium"]};   border: 1px solid {SEVERITY_COLORS["medium"]}55;   border-radius: 4px; padding: 2px 8px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }}
        .badge-low      {{ background: {SEVERITY_COLORS["low"]}22;       color: {SEVERITY_COLORS["low"]};       border: 1px solid {SEVERITY_COLORS["low"]}55;       border-radius: 4px; padding: 2px 8px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }}

        /* ── Section headers ── */
        .section-header {{
            color: {TEXT_MUTED};
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            border-bottom: 1px solid {BORDER};
            padding-bottom: 6px;
            margin: 20px 0 12px 0;
        }}

        /* ── Confidence bar labels ── */
        .conf-label {{
            font-size: 0.72rem;
            color: {TEXT_MUTED};
        }}

        /* ── Sidebar styling ── */
        [data-testid="stSidebar"] {{
            background-color: {BG_SECONDARY} !important;
            border-right: 1px solid {BORDER};
        }}

        /* ── Hide Streamlit branding ── */
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        header {{ visibility: hidden; }}

        /* ── DataFrame styling ── */
        .stDataFrame {{ border: 1px solid {BORDER}; border-radius: 6px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def verdict_badge_html(consensus: str) -> str:
    """Return HTML for a colored verdict badge."""
    color = VERDICT_COLORS.get(consensus, NEUTRAL)
    label = VERDICT_LABELS.get(consensus, consensus.upper())
    return (
        f'<span class="verdict-badge" '
        f'style="background:{color}22; color:{color}; border:2px solid {color}77;">'
        f'{label}</span>'
    )


def severity_badge_html(severity: str) -> str:
    """Return HTML for a severity badge."""
    sev = (severity or "low").lower()
    return f'<span class="badge-{sev}">{sev.upper()}</span>'


def stance_color(stance: str) -> str:
    """Return a hex color for an agent stance string."""
    return STANCE_COLORS.get(stance, NEUTRAL)


def stance_class(stance: str) -> str:
    """Return CSS class ('bullish', 'bearish', or 'neutral') for stance border."""
    if "bull" in stance:
        return "bullish"
    if "bear" in stance:
        return "bearish"
    return "neutral"
