"""Council of AI Agents Skill — v0.1

Routes market questions through a 7-agent council (Bull, Bear, Indicator,
Risk, Sentiment, Political, Contrarian) and synthesizes a final verdict.

Intent keywords handled:
    council analyze <topic>     — run full 7-agent debate
    council history             — list recent debates
    council debate <id>         — retrieve a specific debate by ID
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill
from openclaw.skills.council.agents import (
    AGENT_DEFINITIONS,
    CouncilAgent,
    Moderator,
)
from openclaw.skills.council.db import CouncilDB

logger = logging.getLogger(__name__)

_DB_PATH = "/data/council.db"
_DEADLINE = 120  # seconds — return whatever agents finish within this window

_CONSENSUS_ICON = {
    "strong_buy":  "[STRONG BUY]",
    "buy":         "[BUY]",
    "neutral":     "[NEUTRAL]",
    "sell":        "[SELL]",
    "strong_sell": "[STRONG SELL]",
}

_STANCE_ICON = {
    "strongly_bullish":  "[++]",
    "bullish":           "[+]",
    "slightly_bullish":  "[+]",
    "neutral":           "[~]",
    "slightly_bearish":  "[-]",
    "bearish":           "[-]",
    "strongly_bearish":  "[--]",
}


class CouncilSkill(BaseSkill):
    """Council of AI Agents — 7-agent market analysis and debate system.

    All 7 agents run in parallel via asyncio.gather for fast turnaround.
    Results are stored in CouncilDB for history and replay.
    """

    name: ClassVar[str] = "council"
    description: ClassVar[str] = (
        "Council of 7 AI agents that debates market questions and produces consensus verdicts"
    )
    min_tier: ClassVar[int] = 1
    examples: ClassVar[list[str]] = [
        "council analyze Lakers vs Celtics spread",
        "council analyze DKNG stock this week",
        "council history",
        "council debate 5",
    ]

    def __init__(self, store, inference):
        super().__init__(store, inference)
        self._db: CouncilDB | None = None

    @property
    def db(self) -> CouncilDB:
        """Lazy-initialised database instance."""
        if self._db is None:
            self._db = CouncilDB(_DB_PATH)
        return self._db

    # ── Main dispatch ─────────────────────────────────────

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        """Route council commands to the appropriate handler."""
        text = ctx.message.content.strip()
        text_lower = text.lower()

        try:
            # council analyze <topic>
            analyze_match = re.search(r"\bcouncil\s+analyze\s+(.+)$", text_lower)
            if analyze_match:
                topic = analyze_match.group(1).strip()
                # Use original-cased version of topic
                original_idx = text_lower.index(topic)
                topic = text[original_idx:].strip()
                return await self._handle_analyze(ctx, topic)

            # council debate <id>
            debate_match = re.search(r"\bcouncil\s+debate\s+(\d+)\b", text_lower)
            if debate_match:
                debate_id = int(debate_match.group(1))
                return self._handle_debate(debate_id)

            # council history
            if re.search(r"\bcouncil\s+history\b", text_lower):
                return self._handle_history()

            # Generic "council" trigger — show history
            return self._handle_history()

        except Exception as exc:
            logger.exception("CouncilSkill.execute failed")
            self.store.log_audit(
                ctx.message.sender_id,
                "council_error",
                str(exc),
                ctx.user_tier,
            )
            return self._error(f"Council error: {exc}")

    # ── Command handlers ──────────────────────────────────

    async def _handle_analyze(self, ctx: SkillContext, topic: str) -> SkillResponse:
        """Run the 7-agent debate with a hard deadline.

        Ollama processes requests sequentially, so 7 agents on CPU can take
        minutes.  We use asyncio.wait with a deadline: collect as many agent
        opinions as finish within _DEADLINE seconds, then synthesize with
        whatever we have (minimum 1 opinion required).
        """
        # Gather context from sibling skills if available
        context = await self._gather_context(topic)

        # Instantiate agents
        agents = [CouncilAgent(defn, self.inference) for defn in AGENT_DEFINITIONS]

        # Run agents with a deadline — take whatever finishes in time
        logger.info("CouncilSkill: running %d agents on topic=%r (deadline=%ds)",
                     len(agents), topic[:60], _DEADLINE)
        tasks = {
            asyncio.create_task(agent.analyze(topic, context)): agent.name
            for agent in agents
        }

        done, pending = await asyncio.wait(
            tasks.keys(), timeout=_DEADLINE, return_when=asyncio.ALL_COMPLETED
        )

        # Cancel stragglers
        for task in pending:
            task.cancel()
            logger.info("Agent %s cancelled (deadline exceeded)", tasks[task])

        # Collect completed opinions
        valid_opinions = []
        for task in done:
            try:
                op = task.result()
                if not isinstance(op, Exception):
                    valid_opinions.append(op)
            except Exception as exc:
                logger.warning("Agent task failed: %s", exc)

        logger.info("CouncilSkill: %d/%d agents completed within deadline",
                     len(valid_opinions), len(agents))

        if not valid_opinions:
            return self._error(
                f"Council timed out — no agents responded within {_DEADLINE}s. "
                "The local model may still be loading. Try again in a minute."
            )

        # Synthesize verdict — skip LLM summary if we're already tight on time
        # (moderator will fall back to a computed summary if LLM fails)
        moderator = Moderator(self.inference)
        verdict = await moderator.synthesize(topic, valid_opinions)

        # Store in DB
        opinions_dicts = [
            {
                "agent_name": op.agent_name,
                "stance": op.stance,
                "confidence": op.confidence,
                "reasoning": op.reasoning,
                "key_factors": op.key_factors,
            }
            for op in valid_opinions
        ]
        debate_id = self.db.store_debate(
            topic=topic,
            consensus=verdict.consensus,
            confidence=verdict.confidence,
            summary=verdict.summary,
            bull_score=verdict.bull_score,
            bear_score=verdict.bear_score,
            context={"context_snippet": context[:500]} if context else None,
        )
        self.db.store_opinions(debate_id, opinions_dicts)
        verdict.debate_id = debate_id

        self.store.log_audit(
            ctx.message.sender_id,
            "council_debate",
            f"debate_id={debate_id} topic={topic[:60]} consensus={verdict.consensus}",
            ctx.user_tier,
        )

        return self._reply(self._format_verdict(verdict))

    def _handle_history(self) -> SkillResponse:
        """Return the last 10 debate summaries."""
        debates = self.db.get_history(limit=10)
        if not debates:
            return self._reply(
                "Council History\n"
                "━" * 22 + "\n"
                "No debates on record yet.\n"
                "Use 'council analyze <topic>' to start a debate."
            )

        lines = [f"Council Debate History ({len(debates)} recent)", "━" * 22]
        for d in debates:
            icon = _CONSENSUS_ICON.get(d["consensus"], "[?]")
            date = d["created_at"][:10]
            conf = f"{d['confidence']:.0%}"
            lines.append(f"{icon} [{d['id']}] {d['topic'][:55]}")
            lines.append(f"  {date}  confidence={conf}")
            lines.append("")

        lines.append("Use 'council debate <id>' to see full analysis.")
        return self._reply("\n".join(lines).strip())

    def _handle_debate(self, debate_id: int) -> SkillResponse:
        """Return the full record for a specific debate."""
        debate = self.db.get_debate(debate_id)
        if not debate:
            return self._error(f"Debate #{debate_id} not found.")

        opinions = debate.get("opinions", [])
        icon = _CONSENSUS_ICON.get(debate["consensus"], "[?]")
        lines = [
            f"Council Debate #{debate_id}",
            "━" * 22,
            f"Topic: {debate['topic']}",
            f"Verdict: {icon}  confidence={debate['confidence']:.0%}",
            f"Bull: {debate['bull_score']:.2f}  Bear: {debate['bear_score']:.2f}",
            "",
            "Summary:",
            debate.get("summary", ""),
            "",
            f"Agent Opinions ({len(opinions)}):",
        ]
        for op in opinions:
            s_icon = _STANCE_ICON.get(op["stance"], "[?]")
            lines.append(f"  {s_icon} {op['agent_name'].upper()}: {op['reasoning'][:100]}")
        return self._reply("\n".join(lines))

    # ── Context gathering ─────────────────────────────────

    async def _gather_context(self, topic: str) -> str:
        """Gather relevant context from sibling skills to enrich agent analysis."""
        context_parts: list[str] = []

        if self.registry is None:
            return ""

        # Try to pull signals context
        signals_skill = self.registry.get("sports_signals")
        if signals_skill:
            try:
                db = signals_skill.db
                pending = db.get_pending_signals(limit=5)
                if pending:
                    context_parts.append(
                        "Recent signals: " + ", ".join(
                            f"{s.get('team_or_player','?')} {s.get('market','?')}"
                            for s in pending[:3]
                        )
                    )
            except Exception:
                pass

        # Try to pull political context if topic mentions gambling/regulation
        topic_lower = topic.lower()
        if any(kw in topic_lower for kw in ["gambling", "betting", "dkng", "penn", "mgm", "regulation", "bill"]):
            polint_skill = self.registry.get("politician_intel")
            if polint_skill:
                try:
                    db = polint_skill.db
                    alerts = db.get_recent_alerts(days=7, limit=3)
                    if alerts:
                        context_parts.append(
                            "Recent political alerts: " + "; ".join(
                                a.get("title", "") for a in alerts[:2]
                            )
                        )
                except Exception:
                    pass

        return "\n".join(context_parts)

    # ── Formatting ────────────────────────────────────────

    def _format_verdict(self, verdict) -> str:
        """Format a CouncilVerdict for Telegram/WhatsApp."""
        icon = _CONSENSUS_ICON.get(verdict.consensus, "[?]")
        bull_bar = "#" * int(verdict.bull_score * 10)
        bear_bar = "#" * int(verdict.bear_score * 10)

        lines = [
            f"Council Analysis — Debate #{verdict.debate_id}",
            "━" * 22,
            f"Topic: {verdict.topic}",
            "",
            f"Verdict: {icon}",
            f"Confidence: {verdict.confidence:.0%}",
            f"Bull [{bull_bar:<10}] {verdict.bull_score:.2f}",
            f"Bear [{bear_bar:<10}] {verdict.bear_score:.2f}",
            "",
            "Summary:",
            verdict.summary,
            "",
            "Agent Votes:",
        ]

        for op in verdict.agent_opinions:
            s_icon = _STANCE_ICON.get(op.stance, "[?]")
            lines.append(f"  {s_icon} {op.agent_name.upper()} ({op.confidence:.0%}): {op.reasoning[:80]}")

        lines.append("")
        lines.append(f"Full analysis: 'council debate {verdict.debate_id}'")
        return "\n".join(lines)
