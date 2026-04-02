"""Live Odds page — sports odds, line movement, and bookmaker comparison."""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

from utils.theme import inject_custom_css, BULL, BEAR, WARN, ACCENT, BORDER, TEXT_MUTED
import utils.api as api

# ── Page config ───────────────────────────────────────────

st.set_page_config(
    page_title="Live Odds — Prometheus",
    page_icon="🎲",
    layout="wide",
)
inject_custom_css()

# ── Sidebar ───────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📡 Prometheus")
    st.markdown("**Live Odds**")
    st.divider()
    st.markdown("Real-time odds from multiple bookmakers via The Odds API.")
    st.divider()

    # API Quota meter
    # requests_remaining is only returned by the /odds/odds fetch endpoint,
    # not by /odds/sports. We store it in session state whenever an odds fetch
    # is made so the sidebar can display an up-to-date value.
    st.markdown("**API Quota**")
    remaining = st.session_state.get("odds_requests_remaining")
    if remaining is not None and isinstance(remaining, (int, float)):
        # The Odds API free tier = 500/month
        quota_pct = min(float(remaining) / 500.0, 1.0)
        st.progress(quota_pct)
        st.caption(f"{remaining} requests remaining")
    else:
        st.caption("Quota shown after first odds fetch")

# ── Header ────────────────────────────────────────────────

st.markdown("# 🎲 Live Odds")
st.divider()

# ── Load sports list ──────────────────────────────────────

@st.cache_data(ttl=300)
def load_sports():
    try:
        sports = api.get_odds_sports()
        return sports, None
    except RuntimeError as e:
        return [], str(e)


sports_list, sports_err = load_sports()

if sports_err:
    st.error(f"Cannot load sports: {sports_err}")
    st.info("Make sure ODDS_API_KEY is configured in the backend environment.")
    st.stop()

if not sports_list:
    st.warning("No active sports available from The Odds API right now.")
    st.info("Either no events are scheduled, or ODDS_API_KEY is not configured.")
    st.stop()

# ── Sport selector ────────────────────────────────────────

# Build display labels
sport_options = {}
for s in sports_list:
    key = s.get("key", "")
    title = s.get("title", key)
    sport_options[f"{title} ({key})"] = key

selected_label = st.selectbox(
    "Select Sport",
    options=list(sport_options.keys()),
    key="sport_select",
)
selected_sport = sport_options[selected_label]

market_option = st.radio(
    "Market",
    ["h2h", "spreads", "totals"],
    horizontal=True,
    key="market_select",
)

st.divider()

# ── Load events ───────────────────────────────────────────

@st.cache_data(ttl=60)
def load_events(sport: str, markets: str):
    try:
        result = api.get_odds_events(sport=sport, markets=markets)
        return result, None
    except RuntimeError as e:
        return {}, str(e)


with st.spinner(f"Fetching {market_option} odds for {selected_label}..."):
    events_data, events_err = load_events(selected_sport, market_option)

if events_err:
    st.error(f"Error fetching odds: {events_err}")
    st.stop()

events = events_data.get("events", [])
requests_remaining = events_data.get("requests_remaining")
if requests_remaining is not None:
    # Persist quota into session state so the sidebar can display it
    st.session_state["odds_requests_remaining"] = requests_remaining
    st.caption(f"API requests remaining after fetch: {requests_remaining}")

if not events:
    st.info(f"No {market_option} odds available for {selected_label} right now.")
    st.stop()

# ── Events Table ──────────────────────────────────────────

st.markdown(f'<div class="section-header">Events — {len(events)} found</div>', unsafe_allow_html=True)

# Build flat rows from bookmaker odds
rows = []
for event in events:
    home = event.get("home_team", "?")
    away = event.get("away_team", "?")
    commence = event.get("commence_time", "")
    if commence:
        try:
            dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
            commence_str = dt.strftime("%m/%d %H:%M UTC")
        except Exception:
            commence_str = commence[:16]
    else:
        commence_str = ""

    # Collect best odds per outcome across bookmakers
    bookmaker_odds: dict[str, dict[str, float]] = {}
    for bk in event.get("bookmakers", []):
        bk_key = bk.get("key", "")
        for mkt in bk.get("markets", []):
            if mkt.get("key") != market_option:
                continue
            for outcome in mkt.get("outcomes", []):
                name = outcome.get("name", "")
                price = outcome.get("price")
                point = outcome.get("point")
                if bk_key not in bookmaker_odds:
                    bookmaker_odds[bk_key] = {}
                label = f"{name} {point:+.1f}" if point is not None else name
                bookmaker_odds[bk_key][label] = price

    row = {
        "Matchup": f"{away} @ {home}",
        "Start": commence_str,
        "Event ID": event.get("id", ""),
    }

    # Add first 4 bookmakers as columns
    for bk_key, outcomes in list(bookmaker_odds.items())[:4]:
        outcome_str = " | ".join(
            f"{name}: {price}" for name, price in outcomes.items()
        )
        row[bk_key.upper()] = outcome_str

    rows.append(row)

if rows:
    df_events = pd.DataFrame(rows)
    st.dataframe(df_events, use_container_width=True, hide_index=True)

st.divider()

# ── Line Movement ─────────────────────────────────────────

st.markdown('<div class="section-header">Line Movement</div>', unsafe_allow_html=True)

team_names = []
for event in events:
    team_names.append(event.get("home_team", ""))
    team_names.append(event.get("away_team", ""))
team_names = sorted(set(t for t in team_names if t))

movement_col1, movement_col2 = st.columns([2, 1])

with movement_col2:
    selected_team = st.selectbox(
        "Select team for line movement",
        options=team_names,
        key="movement_team",
    )
    movement_market = st.selectbox(
        "Market",
        ["spreads", "h2h", "totals"],
        key="movement_market",
    )
    movement_hours = st.slider("Hours back", 1, 72, 24, key="movement_hours")

with movement_col1:
    if selected_team:
        @st.cache_data(ttl=60)
        def load_movement(team: str, market: str, hours: int):
            try:
                return api.get_odds_movement(team=team, market=market, hours=hours), None
            except RuntimeError as e:
                return {}, str(e)

        mov_data, mov_err = load_movement(selected_team, movement_market, movement_hours)

        if mov_err:
            st.warning(f"Movement data error: {mov_err}")
        else:
            snapshots = mov_data.get("snapshots", [])
            if not snapshots:
                st.info(
                    f"No {movement_market} movement data for {selected_team} in the last "
                    f"{movement_hours}h. Fetch odds a few times to build up history."
                )
            else:
                # Group by bookmaker
                bk_data: dict[str, list] = {}
                for snap in snapshots:
                    bk = snap.get("bookmaker", "unknown")
                    if bk not in bk_data:
                        bk_data[bk] = []
                    bk_data[bk].append(snap)

                fig = go.Figure()
                colors = [ACCENT, BULL, BEAR, WARN, "#a371f7", "#f78166", "#56d364"]
                for i, (bk, snaps) in enumerate(bk_data.items()):
                    snaps_sorted = sorted(snaps, key=lambda x: x.get("recorded_at", ""))
                    times = [s.get("recorded_at", "")[:16] for s in snaps_sorted]
                    prices = [s.get("price", 0) for s in snaps_sorted]
                    fig.add_trace(go.Scatter(
                        x=times,
                        y=prices,
                        mode="lines+markers",
                        name=bk.upper(),
                        line=dict(color=colors[i % len(colors)], width=2),
                        marker=dict(size=5),
                    ))

                fig.update_layout(
                    title=dict(
                        text=f"{selected_team} — {movement_market.upper()} movement ({movement_hours}h)",
                        font=dict(color="#c9d1d9", size=14),
                    ),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#c9d1d9"),
                    legend=dict(font=dict(color="#c9d1d9"), bgcolor="rgba(0,0,0,0)"),
                    xaxis=dict(showgrid=True, gridcolor="#30363d", color="#8b949e"),
                    yaxis=dict(showgrid=True, gridcolor="#30363d", color="#8b949e"),
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=320,
                )
                st.plotly_chart(fig, use_container_width=True)
