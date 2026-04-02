"""Sports Signals page — picks, source performance, and graded results."""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from utils.theme import inject_custom_css, BULL, BEAR, WARN, ACCENT, BORDER, TEXT_MUTED
import utils.api as api

# ── Page config ───────────────────────────────────────────

st.set_page_config(
    page_title="Sports Signals — Prometheus",
    page_icon="🏈",
    layout="wide",
)
inject_custom_css()

# ── Sidebar ───────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📡 Prometheus")
    st.markdown("**Sports Signals**")
    st.divider()
    st.markdown("Ingested picks from all sources, graded results, and source performance rankings.")

# ── Header ────────────────────────────────────────────────

st.markdown("# 🏈 Sports Signals")
st.divider()

# ── Load data ────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_signals_data():
    data = {}
    try:
        data["dashboard"] = api.get_signals_dashboard()
    except RuntimeError as e:
        data["dashboard_err"] = str(e)

    try:
        data["pending"] = api.get_pending_signals()
    except RuntimeError as e:
        data["pending_err"] = str(e)

    try:
        data["sources"] = api.get_sources()
    except RuntimeError as e:
        data["sources_err"] = str(e)

    try:
        data["straights"] = api.get_straights()
    except RuntimeError as e:
        data["straights_err"] = str(e)

    try:
        data["parlays"] = api.get_parlays()
    except RuntimeError as e:
        data["parlays_err"] = str(e)

    try:
        data["results"] = api.get_results()
    except RuntimeError as e:
        data["results_err"] = str(e)

    return data


if st.button("Refresh Data", type="secondary"):
    st.cache_data.clear()

data = load_signals_data()

# Show backend error if dashboard fetch failed
if "dashboard_err" in data:
    st.error(f"Backend error: {data['dashboard_err']}")
    st.stop()

dashboard = data.get("dashboard", {})

# ── KPI Row ───────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Pending Signals", dashboard.get("pending_count", 0))
with col2:
    today_count = dashboard.get("today_count", 0)
    st.metric("Today's Picks", today_count)
with col3:
    wr = dashboard.get("overall_win_rate", 0)
    st.metric("Overall Win Rate", f"{wr:.1%}" if wr else "N/A")
with col4:
    source_count = dashboard.get("source_count", 0)
    st.metric("Active Sources", source_count)

st.divider()

# ── Source Performance ────────────────────────────────────

st.markdown('<div class="section-header">Source Performance</div>', unsafe_allow_html=True)

sources = data.get("sources", [])
if "sources_err" in data:
    st.warning(f"Could not load sources: {data['sources_err']}")
elif not sources:
    st.info("No source performance data yet. Ingest signals to populate this chart.")
else:
    names = [s.get("source", "Unknown") for s in sources]
    wins = [s.get("wins", 0) for s in sources]
    losses = [s.get("losses", 0) for s in sources]
    totals = [s.get("total_picks", 1) for s in sources]
    win_rates = [w / t if t else 0 for w, t in zip(wins, totals)]
    roi_vals = [s.get("roi", 0.0) for s in sources]

    chart_col, table_col = st.columns([2, 1])

    with chart_col:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Wins",
            x=names,
            y=wins,
            marker_color=BULL,
        ))
        fig.add_trace(go.Bar(
            name="Losses",
            x=names,
            y=losses,
            marker_color=BEAR,
        ))
        fig.update_layout(
            barmode="stack",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#c9d1d9"),
            legend=dict(font=dict(color="#c9d1d9"), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(showgrid=False, color="#8b949e"),
            yaxis=dict(showgrid=True, gridcolor="#30363d", color="#8b949e"),
            margin=dict(l=0, r=0, t=10, b=10),
            height=280,
        )
        st.plotly_chart(fig, use_container_width=True)

    with table_col:
        df_sources = pd.DataFrame({
            "Source": names,
            "W": wins,
            "L": losses,
            "Win %": [f"{r:.1%}" for r in win_rates],
            "ROI": [f"{r:+.1f}%" if r else "N/A" for r in roi_vals],
        })
        st.dataframe(df_sources, use_container_width=True, hide_index=True)

st.divider()

# ── Today's Picks ─────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["Pending Picks", "Straight Bets", "Parlays"])

with tab1:
    pending = data.get("pending", [])
    if "pending_err" in data:
        st.warning(f"Could not load pending: {data['pending_err']}")
    elif not pending:
        st.info("No pending signals. Use the ingest endpoint or send signals via chat.")
    else:
        rows = []
        for s in pending:
            rows.append({
                "ID": s.get("id", ""),
                "Team / Player": s.get("team_or_player", ""),
                "Market": s.get("market", ""),
                "Line": s.get("line", ""),
                "Odds": s.get("odds", ""),
                "Units": s.get("units", 1.0),
                "Source": s.get("source", ""),
                "Date": str(s.get("created_at", ""))[:10],
            })
        df_pending = pd.DataFrame(rows)
        st.dataframe(df_pending, use_container_width=True, hide_index=True)

with tab2:
    straights = data.get("straights", [])
    if "straights_err" in data:
        st.warning(f"Could not load straight bets: {data['straights_err']}")
    elif not straights:
        st.info("No straight bet recommendations available.")
    else:
        rows = []
        for s in straights:
            confidence = s.get("confidence", s.get("score", 0))
            rows.append({
                "Team / Player": s.get("team_or_player", s.get("pick", "")),
                "Market": s.get("market", ""),
                "Odds": s.get("odds", ""),
                "Units": s.get("units", 1),
                "Confidence": f"{confidence:.0%}" if isinstance(confidence, float) else confidence,
                "Source": s.get("source", ""),
            })
        df_straights = pd.DataFrame(rows)
        st.dataframe(df_straights, use_container_width=True, hide_index=True)

with tab3:
    parlays = data.get("parlays", [])
    if "parlays_err" in data:
        st.warning(f"Could not load parlays: {data['parlays_err']}")
    elif not parlays:
        st.info("No parlay recommendations available.")
    else:
        for i, parlay in enumerate(parlays[:10]):
            legs = parlay.get("legs", [])
            ev = parlay.get("expected_value", parlay.get("ev", ""))
            header = f"Parlay #{i+1} — {len(legs)} legs"
            if ev:
                header += f" | EV: {ev}"
            with st.expander(header):
                for leg in legs:
                    st.markdown(
                        f"- **{leg.get('team_or_player', '?')}** "
                        f"{leg.get('market', '')} @ {leg.get('odds', '')}"
                    )

st.divider()

# ── Graded Results ────────────────────────────────────────

st.markdown('<div class="section-header">Graded Results</div>', unsafe_allow_html=True)

results = data.get("results", [])
if "results_err" in data:
    st.warning(f"Could not load results: {data['results_err']}")
elif not results:
    st.info("No graded results for today. Results appear once signals are graded via the API.")
else:
    rows = []
    for r in results:
        status = r.get("status", "")
        rows.append({
            "Team / Player": r.get("team_or_player", ""),
            "Market": r.get("market", ""),
            "Odds": r.get("odds", ""),
            "Units": r.get("units", 1),
            "Result": status.upper() if status else "",
            "Source": r.get("source", ""),
        })
    df_results = pd.DataFrame(rows)

    def highlight_result(val):
        if val == "WIN":
            return f"color: {BULL}; font-weight: bold"
        elif val == "LOSS":
            return f"color: {BEAR}; font-weight: bold"
        elif val == "PUSH":
            return f"color: {WARN}; font-weight: bold"
        return ""

    st.dataframe(
        df_results.style.map(highlight_result, subset=["Result"]),
        use_container_width=True,
        hide_index=True,
    )
