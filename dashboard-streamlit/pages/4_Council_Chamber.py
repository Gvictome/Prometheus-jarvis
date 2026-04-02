"""Council Chamber — 7-agent AI debate interface with radar chart and history."""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import math

from utils.theme import (
    inject_custom_css,
    verdict_badge_html, stance_color, stance_class,
    AGENT_EMOJIS, AGENT_DISPLAY,
    VERDICT_COLORS, VERDICT_LABELS,
    BULL, BEAR, WARN, ACCENT, BORDER, BG_SECONDARY, TEXT_MUTED,
    NEUTRAL,
)
import utils.api as api

# ── Page config ───────────────────────────────────────────

st.set_page_config(
    page_title="Council Chamber — Prometheus",
    page_icon="🤖",
    layout="wide",
)
inject_custom_css()

# ── Sidebar ───────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📡 Prometheus")
    st.markdown("**Council Chamber**")
    st.divider()
    st.markdown(
        "Seven specialist AI agents independently analyze any market question. "
        "A Moderator synthesizes their views into a final verdict."
    )
    st.divider()

    # Agent roster
    st.markdown("**Agent Roster**")
    agents_list = [
        ("bull",       "Bull Agent",       "Upside catalysts"),
        ("bear",       "Bear Agent",       "Downside risks"),
        ("indicator",  "Indicator Agent",  "Technical signals"),
        ("risk",       "Risk Agent",       "Risk/reward sizing"),
        ("sentiment",  "Sentiment Agent",  "Public sentiment"),
        ("political",  "Political Agent",  "Regulatory landscape"),
        ("contrarian", "Contrarian Agent", "Devil's advocate"),
    ]
    for name, display, role in agents_list:
        emoji = AGENT_EMOJIS.get(name, "")
        st.markdown(f"{emoji} **{display}** — {role}")

# ── Header ────────────────────────────────────────────────

st.markdown("# 🤖 Council Chamber")
st.markdown(
    '<p style="color:#8b949e; margin-top:-10px;">Submit a market question — all 7 agents deliberate in parallel</p>',
    unsafe_allow_html=True,
)
st.divider()

# ── Chat Interface ────────────────────────────────────────

st.markdown('<div class="section-header">Ask the Council</div>', unsafe_allow_html=True)

input_col, btn_col = st.columns([5, 1])
with input_col:
    query = st.text_input(
        "Market question",
        placeholder="e.g. Should I bet Lakers -3.5 tonight? / Is DKNG stock a buy this week?",
        label_visibility="collapsed",
        key="council_query",
    )
with btn_col:
    submit = st.button("Analyze", type="primary", use_container_width=True)

# Example prompts
example_col1, example_col2, example_col3 = st.columns(3)
with example_col1:
    if st.button("Lakers -3.5 tonight", use_container_width=True):
        st.session_state["council_query"] = "Should I bet Lakers -3.5 tonight?"
        st.rerun()
with example_col2:
    if st.button("DKNG stock outlook", use_container_width=True):
        st.session_state["council_query"] = "Is DraftKings (DKNG) stock a buy this week?"
        st.rerun()
with example_col3:
    if st.button("NFL spread value", use_container_width=True):
        st.session_state["council_query"] = "Is there value on NFL spread bets this weekend?"
        st.rerun()

# ── Debate execution ──────────────────────────────────────

if submit and query.strip():
    with st.spinner("Council is deliberating... (this takes 15-30 seconds)"):
        try:
            result = api.post_council_analyze(query.strip())
            st.session_state["last_debate"] = result
            st.session_state["last_query"] = query.strip()
        except RuntimeError as e:
            st.error(f"Council error: {e}")
            result = None

# ── Display last debate result ────────────────────────────

debate_result = st.session_state.get("last_debate")

if debate_result:
    st.divider()
    consensus = debate_result.get("consensus", "neutral")
    confidence = debate_result.get("confidence", 0.0)
    summary = debate_result.get("summary", "")
    bull_score = debate_result.get("bull_score", 0.0)
    bear_score = debate_result.get("bear_score", 0.0)
    debate_id = debate_result.get("debate_id")
    topic = debate_result.get("topic", st.session_state.get("last_query", ""))
    opinions = debate_result.get("agent_opinions", [])

    # ── Verdict header ─────────────────────────────────────

    verdict_col, conf_col, scores_col = st.columns([2, 2, 2])

    with verdict_col:
        st.markdown("**Council Verdict**")
        badge_html = verdict_badge_html(consensus)
        if debate_id:
            badge_html += f'<br><span style="color:#8b949e; font-size:0.75rem;">Debate #{debate_id}</span>'
        st.markdown(badge_html, unsafe_allow_html=True)

    with conf_col:
        st.markdown("**Confidence**")
        st.progress(confidence)
        st.caption(f"{confidence:.0%} overall confidence")

    with scores_col:
        st.markdown("**Bull / Bear Scores**")
        bull_pct = int(bull_score * 100)
        bear_pct = int(bear_score * 100)
        st.markdown(
            f'<div style="display:flex; gap:12px; align-items:center; margin-top:6px;">'
            f'<span style="color:{BULL}; font-weight:700; font-size:1.1rem;">▲ {bull_pct}%</span>'
            f'<span style="color:{BEAR}; font-weight:700; font-size:1.1rem;">▼ {bear_pct}%</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("")
    st.markdown(f"**Topic:** {topic}")
    if summary:
        st.markdown(
            f'<div class="prom-card" style="margin-top:10px;">'
            f'<div class="prom-card-title">Moderator Summary</div>'
            f'<p style="color:#c9d1d9; margin:6px 0 0 0; line-height:1.6;">{summary}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Agent Cards ────────────────────────────────────────

    st.divider()
    st.markdown('<div class="section-header">Agent Opinions</div>', unsafe_allow_html=True)

    if opinions:
        # 4 cards in first row, 3 in second (or use columns of 4 and wrap)
        cols_per_row = 4
        for row_start in range(0, len(opinions), cols_per_row):
            row_opinions = opinions[row_start:row_start + cols_per_row]
            cols = st.columns(cols_per_row)
            for col, op in zip(cols, row_opinions):
                with col:
                    name = op.get("agent_name", "")
                    stance = op.get("stance", "neutral")
                    conf = op.get("confidence", 0.0)
                    reasoning = op.get("reasoning", "")
                    key_factors = op.get("key_factors", [])
                    emoji = AGENT_EMOJIS.get(name, "🤖")
                    display = AGENT_DISPLAY.get(name, name.capitalize())
                    css_class = stance_class(stance)
                    s_color = stance_color(stance)
                    stance_label = stance.replace("_", " ").upper()

                    factors_html = ""
                    if key_factors:
                        factors_html = "<ul style='margin:4px 0 0 0; padding-left:16px; color:#8b949e; font-size:0.78rem;'>"
                        for f in key_factors[:3]:
                            factors_html += f"<li>{f}</li>"
                        factors_html += "</ul>"

                    st.markdown(
                        f"""<div class="agent-card {css_class}">
                            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                                <span class="agent-name">{emoji} {display}</span>
                                <span style="color:{s_color}; font-size:0.72rem; font-weight:600; text-align:right;">{stance_label}</span>
                            </div>
                            <div style="margin:8px 0 4px 0;">
                                <div style="background:#30363d; border-radius:4px; height:5px; overflow:hidden;">
                                    <div style="background:{s_color}; width:{int(conf*100)}%; height:100%; border-radius:4px;"></div>
                                </div>
                                <span class="conf-label">{conf:.0%} confidence</span>
                            </div>
                            <p style="color:#c9d1d9; font-size:0.8rem; margin:6px 0 0 0; line-height:1.5;">{reasoning[:120]}{"..." if len(reasoning) > 120 else ""}</p>
                            {factors_html}
                        </div>""",
                        unsafe_allow_html=True,
                    )

    # ── Visualizations ─────────────────────────────────────

    st.divider()
    viz_col1, viz_col2 = st.columns(2)

    with viz_col1:
        st.markdown('<div class="section-header">Agent Confidence Radar</div>', unsafe_allow_html=True)

        if opinions:
            agent_names_radar = [
                f"{AGENT_EMOJIS.get(op.get('agent_name',''), '')} {op.get('agent_name','').capitalize()}"
                for op in opinions
            ]
            conf_values = [op.get("confidence", 0.0) for op in opinions]
            # Close the polygon
            agent_names_radar_closed = agent_names_radar + [agent_names_radar[0]]
            conf_closed = conf_values + [conf_values[0]]

            fig_radar = go.Figure(go.Scatterpolar(
                r=conf_closed,
                theta=agent_names_radar_closed,
                fill="toself",
                fillcolor=f"rgba(88,166,255,0.15)",
                line=dict(color=ACCENT, width=2),
                marker=dict(color=ACCENT, size=7),
            ))
            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 1],
                        tickformat=".0%",
                        gridcolor="#30363d",
                        linecolor="#30363d",
                        tickfont=dict(color="#8b949e", size=10),
                    ),
                    angularaxis=dict(
                        gridcolor="#30363d",
                        linecolor="#30363d",
                        tickfont=dict(color="#c9d1d9", size=11),
                    ),
                    bgcolor="rgba(0,0,0,0)",
                ),
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c9d1d9"),
                margin=dict(l=60, r=60, t=20, b=20),
                height=360,
            )
            st.plotly_chart(fig_radar, use_container_width=True)
        else:
            st.info("No agent opinions to visualize.")

    with viz_col2:
        st.markdown('<div class="section-header">Consensus Gauge</div>', unsafe_allow_html=True)

        gauge_color = VERDICT_COLORS.get(consensus, NEUTRAL)
        verdict_label = VERDICT_LABELS.get(consensus, consensus.upper())

        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=round(confidence * 100, 1),
            number=dict(suffix="%", font=dict(color="#c9d1d9", size=40)),
            delta=dict(
                reference=50,
                increasing=dict(color=BULL),
                decreasing=dict(color=BEAR),
            ),
            gauge=dict(
                axis=dict(
                    range=[0, 100],
                    tickcolor="#8b949e",
                    tickfont=dict(color="#8b949e"),
                ),
                bar=dict(color=gauge_color, thickness=0.25),
                bgcolor="#161b22",
                borderwidth=1,
                bordercolor="#30363d",
                steps=[
                    dict(range=[0, 33], color="#0d1117"),
                    dict(range=[33, 66], color="#161b22"),
                    dict(range=[66, 100], color="#1f2937"),
                ],
                threshold=dict(
                    line=dict(color=gauge_color, width=3),
                    thickness=0.75,
                    value=round(confidence * 100, 1),
                ),
            ),
            title=dict(
                text=f"Verdict: {verdict_label}<br>"
                     f"<span style='font-size:0.9em; color:#8b949e;'>"
                     f"Bull {bull_score:.2f} / Bear {bear_score:.2f}</span>",
                font=dict(color="#c9d1d9", size=15),
            ),
        ))
        fig_gauge.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#c9d1d9"),
            margin=dict(l=30, r=30, t=60, b=20),
            height=360,
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

# ── Debate History ────────────────────────────────────────

st.divider()
st.markdown('<div class="section-header">Debate History</div>', unsafe_allow_html=True)


@st.cache_data(ttl=60)
def load_history():
    try:
        return api.get_council_history(limit=20), None
    except RuntimeError as e:
        return [], str(e)


history, history_err = load_history()

if history_err:
    st.warning(f"Could not load debate history: {history_err}")
elif not history:
    st.info("No past debates yet. Submit a question above to start the first council session.")
else:
    st.markdown(f"Showing **{len(history)}** most recent debates")

    for debate in history:
        d_id = debate.get("id", "")
        d_topic = debate.get("topic", "Unknown topic")
        d_consensus = debate.get("consensus", "neutral")
        d_conf = debate.get("confidence", 0.0)
        d_date = str(debate.get("created_at", ""))[:16]
        d_color = VERDICT_COLORS.get(d_consensus, NEUTRAL)
        d_label = VERDICT_LABELS.get(d_consensus, d_consensus.upper())

        header_label = (
            f"#{d_id} — {d_topic[:70]} | "
            f"{d_label} ({d_conf:.0%}) | {d_date}"
        )

        with st.expander(header_label):
            st.markdown(
                f'<span style="color:{d_color}; font-weight:700; font-size:1.05rem;">{d_label}</span>'
                f' &nbsp; <span style="color:#8b949e; font-size:0.85rem;">{d_conf:.0%} confidence</span>',
                unsafe_allow_html=True,
            )

            if d_id:
                if st.button(f"Load Full Debate #{d_id}", key=f"load_debate_{d_id}"):
                    with st.spinner(f"Loading debate #{d_id}..."):
                        try:
                            full = api.get_council_debate(int(d_id))
                            full_opinions = full.get("opinions", [])
                            st.markdown(f"**Summary:** {full.get('summary', 'N/A')}")
                            st.markdown(
                                f"Bull: **{full.get('bull_score', 0):.2f}** | "
                                f"Bear: **{full.get('bear_score', 0):.2f}**"
                            )
                            if full_opinions:
                                st.markdown("**Agent Votes:**")
                                for op in full_opinions:
                                    name = op.get("agent_name", "")
                                    stance = op.get("stance", "neutral")
                                    conf = op.get("confidence", 0.0)
                                    reasoning = op.get("reasoning", "")
                                    emoji = AGENT_EMOJIS.get(name, "")
                                    s_color = stance_color(stance)
                                    st.markdown(
                                        f'{emoji} **{name.capitalize()}** '
                                        f'<span style="color:{s_color};">{stance.replace("_"," ").upper()}</span> '
                                        f'({conf:.0%}) — {reasoning}',
                                        unsafe_allow_html=True,
                                    )
                        except RuntimeError as e:
                            st.error(str(e))

            # Show summary inline if present
            summary_text = debate.get("summary", "")
            if summary_text:
                st.markdown(f"*{summary_text[:300]}{'...' if len(summary_text) > 300 else ''}*")
