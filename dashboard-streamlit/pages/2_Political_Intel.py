"""Political Intel page — alerts, trades, bills, and politician profiles."""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from utils.theme import (
    inject_custom_css, severity_badge_html,
    BULL, BEAR, WARN, ACCENT, BORDER, TEXT_MUTED, SEVERITY_COLORS,
)
import utils.api as api

# ── Page config ───────────────────────────────────────────

st.set_page_config(
    page_title="Political Intel — Prometheus",
    page_icon="🏛️",
    layout="wide",
)
inject_custom_css()

# ── Sidebar ───────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📡 Prometheus")
    st.markdown("**Political Intel**")
    st.divider()
    st.markdown("Congressional trades, legislation, and political risk monitoring.")
    st.divider()

    if st.button("Run Congress Collection", type="primary", use_container_width=True):
        with st.spinner("Collecting from Congress.gov..."):
            try:
                result = api.post_collect()
                st.success(
                    f"Collection complete: {result.get('members_upserted', 0)} members, "
                    f"{result.get('bills_stored', 0)} bills."
                )
            except RuntimeError as e:
                st.error(str(e))

    st.markdown("")
    st.caption("Pulls latest member data and bills from Congress.gov API.")

# ── Header ────────────────────────────────────────────────

st.markdown("# 🏛️ Political Intel")
st.divider()

# ── Load data ────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_politics_data():
    data = {}
    try:
        data["dashboard"] = api.get_politics_dashboard()
    except RuntimeError as e:
        data["dashboard_err"] = str(e)

    try:
        data["alerts"] = api.get_alerts(limit=50)
    except RuntimeError as e:
        data["alerts_err"] = str(e)

    try:
        data["trades"] = api.get_trades(days=90, limit=100)
    except RuntimeError as e:
        data["trades_err"] = str(e)

    try:
        data["bills"] = api.get_bills(min_score=0.3, limit=100)
    except RuntimeError as e:
        data["bills_err"] = str(e)

    return data


if st.button("Refresh Data", type="secondary"):
    st.cache_data.clear()

data = load_politics_data()

if "dashboard_err" in data:
    st.error(f"Backend error: {data['dashboard_err']}")
    st.stop()

dashboard = data.get("dashboard", {})

# ── KPI Row ───────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

with col1:
    critical = dashboard.get("critical_alerts_7d", 0)
    st.metric("Critical Alerts (7d)", critical)
with col2:
    st.metric("Total Trades (90d)", dashboard.get("gaming_trades_90d", 0))
with col3:
    st.metric("Relevant Bills", dashboard.get("relevant_bills", 0))
with col4:
    st.metric("Politicians Tracked", dashboard.get("tracked_politicians", 0))

st.divider()

# ── Tabs ──────────────────────────────────────────────────

tab_alerts, tab_trades, tab_bills, tab_search = st.tabs(["Alerts", "Trades", "Bills", "Search"])

# ── Alerts tab ────────────────────────────────────────────

with tab_alerts:
    alerts = data.get("alerts", [])
    if "alerts_err" in data:
        st.warning(f"Could not load alerts: {data['alerts_err']}")
    elif not alerts:
        st.info(
            "No recent alerts. Run a collection to pull the latest congressional data, "
            "or wait for the system to detect new activity."
        )
    else:
        # Severity filter
        sev_options = ["All", "critical", "high", "medium", "low"]
        selected_sev = st.selectbox("Filter by severity", sev_options, key="alert_sev_filter")

        filtered = alerts
        if selected_sev != "All":
            filtered = [a for a in alerts if a.get("severity", "").lower() == selected_sev]

        st.markdown(f"Showing **{len(filtered)}** alerts")

        for alert in filtered:
            severity = alert.get("severity", "low")
            title = alert.get("title", alert.get("message", "Alert"))
            politician = alert.get("politician_name", "")
            detail = alert.get("detail", alert.get("body", ""))
            created = str(alert.get("created_at", ""))[:16]

            badge = severity_badge_html(severity)
            pol_line = f"<br><span style='color:#8b949e; font-size:0.8rem;'>Politician: {politician}</span>" if politician else ""
            time_line = f"<span style='color:#8b949e; font-size:0.75rem;'>{created}</span>" if created else ""

            st.markdown(
                f"""<div class="prom-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span class="prom-card-title">{title}</span>
                        {badge}
                    </div>
                    {pol_line}
                    {time_line}
                    {"<br><span style='color:#c9d1d9; font-size:0.85rem; margin-top:6px; display:block;'>" + detail[:200] + "</span>" if detail else ""}
                </div>""",
                unsafe_allow_html=True,
            )

# ── Trades tab ────────────────────────────────────────────

with tab_trades:
    trades = data.get("trades", [])
    if "trades_err" in data:
        st.warning(f"Could not load trades: {data['trades_err']}")
    elif not trades:
        st.info("No gaming stock trades on file. Run a collection to pull recent filings.")
    else:
        chart_col, detail_col = st.columns([2, 1])

        with chart_col:
            # Treemap: trade amounts by politician
            pol_names = []
            pol_amounts = []
            for t in trades:
                name = t.get("politician_name", "Unknown")
                amount_str = t.get("amount", "0")
                # Amount is often a string range like "$1,001 - $15,000"
                try:
                    # Extract first number
                    import re
                    nums = re.findall(r"[\d,]+", str(amount_str))
                    amount = int(nums[0].replace(",", "")) if nums else 0
                except Exception:
                    amount = 0
                pol_names.append(name)
                pol_amounts.append(amount)

            if any(a > 0 for a in pol_amounts):
                fig = go.Figure(go.Treemap(
                    labels=pol_names,
                    parents=[""] * len(pol_names),
                    values=pol_amounts,
                    marker=dict(
                        colorscale=[[0, "#161b22"], [1, ACCENT]],
                        line=dict(color="#30363d", width=1),
                    ),
                    textfont=dict(color="#c9d1d9"),
                    hovertemplate="<b>%{label}</b><br>Min amount: $%{value:,}<extra></extra>",
                ))
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#c9d1d9"),
                    margin=dict(l=0, r=0, t=10, b=10),
                    height=320,
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Trade amounts not available for chart display.")

        with detail_col:
            # Summary by politician
            pol_trade_counts: dict[str, int] = {}
            for t in trades:
                n = t.get("politician_name", "Unknown")
                pol_trade_counts[n] = pol_trade_counts.get(n, 0) + 1
            df_summary = pd.DataFrame(
                [{"Politician": k, "Trades": v} for k, v in
                 sorted(pol_trade_counts.items(), key=lambda x: -x[1])]
            )
            st.dataframe(df_summary, use_container_width=True, hide_index=True)

        st.markdown("**All Trades**")
        rows = []
        for t in trades:
            rows.append({
                "Politician": t.get("politician_name", ""),
                "Ticker": t.get("ticker", ""),
                "Type": t.get("trade_type", t.get("type", "")),
                "Amount": t.get("amount", ""),
                "Filed": str(t.get("filed_date", t.get("created_at", "")))[:10],
            })
        df_trades = pd.DataFrame(rows)
        st.dataframe(df_trades, use_container_width=True, hide_index=True)

# ── Bills tab ─────────────────────────────────────────────

with tab_bills:
    bills = data.get("bills", [])
    if "bills_err" in data:
        st.warning(f"Could not load bills: {data['bills_err']}")
    elif not bills:
        st.info("No relevant bills found. Run a collection to pull from Congress.gov.")
    else:
        rows = []
        for b in bills:
            score = b.get("relevance_score", b.get("score", 0))
            status = b.get("status", b.get("latest_action", ""))
            rows.append({
                "Title": b.get("title", "")[:80],
                "Bill #": b.get("bill_number", b.get("number", "")),
                "Sponsor": b.get("sponsor", ""),
                "Status": str(status)[:50],
                "Relevance": f"{score:.0%}" if isinstance(score, float) else str(score),
                "Introduced": str(b.get("introduced_date", b.get("date", "")))[:10],
            })
        df_bills = pd.DataFrame(rows)
        st.dataframe(df_bills, use_container_width=True, hide_index=True)

# ── Search tab ────────────────────────────────────────────

with tab_search:
    st.markdown("**Search Politician Profile**")
    search_col, btn_col = st.columns([4, 1])
    with search_col:
        search_name = st.text_input(
            "Politician name",
            placeholder="e.g. Nancy Pelosi",
            label_visibility="collapsed",
        )
    with btn_col:
        do_search = st.button("Search", type="primary", use_container_width=True)

    if do_search and search_name.strip():
        with st.spinner(f"Looking up {search_name}..."):
            try:
                profile_data = api.get_profile(search_name.strip())
                politician = profile_data.get("politician", {})
                trades_list = profile_data.get("trades", [])
                matches = profile_data.get("matches", 0)

                st.markdown(f"Found **{matches}** match(es). Showing top result.")

                info_col, trade_col = st.columns([1, 2])
                with info_col:
                    st.markdown(f"### {politician.get('name', 'Unknown')}")
                    st.markdown(f"**Party:** {politician.get('party', 'N/A')}")
                    st.markdown(f"**State:** {politician.get('state', 'N/A')}")
                    st.markdown(f"**Chamber:** {politician.get('chamber', 'N/A')}")
                    st.markdown(f"**District:** {politician.get('district', 'N/A')}")

                with trade_col:
                    st.markdown("**Recent Gaming Trades**")
                    if trades_list:
                        df_pt = pd.DataFrame([{
                            "Ticker": t.get("ticker", ""),
                            "Type": t.get("trade_type", t.get("type", "")),
                            "Amount": t.get("amount", ""),
                            "Filed": str(t.get("filed_date", ""))[:10],
                        } for t in trades_list])
                        st.dataframe(df_pt, use_container_width=True, hide_index=True)
                    else:
                        st.info("No gaming-related trades on file for this politician.")

            except RuntimeError as e:
                st.error(str(e))
    elif do_search:
        st.warning("Please enter a politician name.")
