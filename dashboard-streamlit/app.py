"""Prometheus Market Intelligence — Streamlit Command Center (Home Page)."""

from __future__ import annotations

import sys
import os

# Ensure utils is importable from pages/
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import plotly.graph_objects as go

from utils.theme import inject_custom_css, BULL, BEAR, WARN, ACCENT, BG_SECONDARY, BORDER, TEXT_MUTED
import utils.api as api

# ── Page config ───────────────────────────────────────────

st.set_page_config(
    page_title="Prometheus",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()

# ── Sidebar ───────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📡 Prometheus")
    st.markdown("**Market Intelligence Platform**")
    st.divider()
    st.markdown("**Navigation**")
    st.markdown("- 🏠 Command Center *(this page)*")
    st.markdown("- 🏈 [Sports Signals](Sports_Signals)")
    st.markdown("- 🏛️ [Political Intel](Political_Intel)")
    st.markdown("- 🎲 [Live Odds](Live_Odds)")
    st.markdown("- 🤖 [Council Chamber](Council_Chamber)")
    st.divider()

    # Platform status
    st.markdown("**Platform Status**")
    try:
        health = api.get_health()
        services = health.get("services", {})
        for svc, status in services.items():
            icon = "🟢" if status == "ok" else "🟡" if "configured" in status.lower() else "🔴"
            st.markdown(f"{icon} `{svc}`: {status}")
    except RuntimeError as e:
        st.error(f"Backend offline: {e}")

# ── Header ────────────────────────────────────────────────

st.markdown("# 📡 Prometheus Market Intelligence")
st.markdown(
    '<p style="color:#8b949e; margin-top:-10px;">Command Center — live signals, political intel, council analysis</p>',
    unsafe_allow_html=True,
)
st.divider()

# ── KPI Row ───────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_kpi_data():
    results = {}
    try:
        results["signals"] = api.get_signals_dashboard()
    except RuntimeError as e:
        results["signals_err"] = str(e)

    try:
        results["politics"] = api.get_politics_dashboard()
    except RuntimeError as e:
        results["politics_err"] = str(e)

    try:
        results["council"] = api.get_council_history(limit=5)
    except RuntimeError as e:
        results["council_err"] = str(e)

    return results


kpi = load_kpi_data()

col1, col2, col3, col4, col5, col6 = st.columns(6)

signals_data = kpi.get("signals", {})
politics_data = kpi.get("politics", {})
council_debates = kpi.get("council", [])

with col1:
    pending = signals_data.get("pending_count", 0) if signals_data else 0
    st.metric("Pending Signals", pending)

with col2:
    win_rate = signals_data.get("overall_win_rate", 0) if signals_data else 0
    st.metric("Win Rate", f"{win_rate:.1%}" if win_rate else "N/A")

with col3:
    critical = politics_data.get("critical_alerts_7d", 0) if politics_data else 0
    high = politics_data.get("high_alerts_7d", 0) if politics_data else 0
    st.metric("Active Alerts (7d)", critical + high, delta=f"{critical} critical" if critical else None)

with col4:
    tracked = politics_data.get("tracked_politicians", 0) if politics_data else 0
    st.metric("Politicians Tracked", tracked)

with col5:
    st.metric("Council Debates", len(council_debates))

with col6:
    # requests_remaining is only returned by /odds/odds (not /odds/sports).
    # Read from session state if the Live Odds page populated it this session.
    remaining = st.session_state.get("odds_requests_remaining", "N/A")
    st.metric("Odds API Quota", remaining)

st.divider()

# ── Charts row ────────────────────────────────────────────

left_col, right_col = st.columns([3, 2])

with left_col:
    st.markdown('<div class="section-header">Source Performance</div>', unsafe_allow_html=True)
    try:
        sources_raw = kpi.get("signals", {}).get("sources", [])
        if sources_raw:
            names = [s.get("source", "Unknown") for s in sources_raw]
            wins = [s.get("wins", 0) for s in sources_raw]
            total = [s.get("total_picks", 1) for s in sources_raw]
            wr = [w / t if t else 0 for w, t in zip(wins, total)]

            fig = go.Figure(go.Bar(
                x=wr,
                y=names,
                orientation="h",
                marker=dict(
                    color=wr,
                    colorscale=[[0, BEAR], [0.5, WARN], [1, BULL]],
                    cmin=0,
                    cmax=1,
                ),
                text=[f"{v:.1%}" for v in wr],
                textposition="outside",
                textfont=dict(color="#c9d1d9", size=11),
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c9d1d9"),
                xaxis=dict(
                    showgrid=True, gridcolor="#30363d",
                    tickformat=".0%", range=[0, 1.1],
                    color="#8b949e",
                ),
                yaxis=dict(showgrid=False, color="#8b949e"),
                margin=dict(l=0, r=40, t=10, b=10),
                height=240,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No source performance data yet. Ingest some signals to get started.")
    except Exception as e:
        st.warning(f"Could not load source chart: {e}")

with right_col:
    st.markdown('<div class="section-header">Latest Council Confidence</div>', unsafe_allow_html=True)
    try:
        latest_conf = 0.0
        latest_consensus = "neutral"
        if council_debates:
            latest = council_debates[0]
            latest_conf = latest.get("confidence", 0.0)
            latest_consensus = latest.get("consensus", "neutral")

        from utils.theme import VERDICT_COLORS
        gauge_color = VERDICT_COLORS.get(latest_consensus, WARN)

        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=round(latest_conf * 100, 1),
            number=dict(suffix="%", font=dict(color="#c9d1d9", size=32)),
            gauge=dict(
                axis=dict(range=[0, 100], tickcolor="#8b949e", tickfont=dict(color="#8b949e")),
                bar=dict(color=gauge_color),
                bgcolor="#161b22",
                borderwidth=1,
                bordercolor="#30363d",
                steps=[
                    dict(range=[0, 40], color="#0d1117"),
                    dict(range=[40, 70], color="#161b22"),
                    dict(range=[70, 100], color="#1f2937"),
                ],
            ),
            title=dict(
                text=f"Council: {latest_consensus.replace('_', ' ').upper()}" if council_debates else "No debates yet",
                font=dict(color="#8b949e", size=13),
            ),
        ))
        fig_gauge.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#c9d1d9"),
            margin=dict(l=20, r=20, t=40, b=10),
            height=240,
        )
        st.plotly_chart(fig_gauge, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load gauge: {e}")

st.divider()

# ── Recent Activity Feed ──────────────────────────────────

st.markdown('<div class="section-header">Recent Activity</div>', unsafe_allow_html=True)

try:
    activity_rows = []

    # Pull recent pending signals
    try:
        pending_sigs = api.get_pending_signals()
        for s in pending_sigs[:5]:
            activity_rows.append({
                "Type": "Signal",
                "Description": f"{s.get('team_or_player', '?')} — {s.get('market', '?')}",
                "Source": s.get("source", ""),
                "Detail": f"Odds: {s.get('odds', 'N/A')}",
                "Time": str(s.get("created_at", ""))[:16],
            })
    except RuntimeError:
        pass

    # Pull recent alerts
    try:
        alerts = api.get_alerts(limit=5)
        for a in alerts[:5]:
            activity_rows.append({
                "Type": "Alert",
                "Description": a.get("title", a.get("message", "Alert")),
                "Source": a.get("severity", ""),
                "Detail": a.get("politician_name", ""),
                "Time": str(a.get("created_at", ""))[:16],
            })
    except RuntimeError:
        pass

    # Pull recent council debates
    for d in council_debates[:3]:
        activity_rows.append({
            "Type": "Council",
            "Description": d.get("topic", "Debate"),
            "Source": d.get("consensus", "").replace("_", " ").upper(),
            "Detail": f"{d.get('confidence', 0):.0%} confidence",
            "Time": str(d.get("created_at", ""))[:16],
        })

    if activity_rows:
        import pandas as pd
        df = pd.DataFrame(activity_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No recent activity. Connect the backend and start adding signals.")

except Exception as e:
    st.error(f"Activity feed error: {e}")
