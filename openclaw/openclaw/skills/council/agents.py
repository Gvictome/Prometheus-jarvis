"""Council of AI Agents — Agent definitions and opinion synthesis.

Seven specialist agents independently analyze a market question, then a
Moderator synthesizes their opinions into a 5-level consensus verdict.

Agent roster:
  1. Bull       — reasons for upside, positive catalysts
  2. Bear       — downside risks, negative factors
  3. Indicator  — technical analysis, trend signals
  4. Risk       — risk/reward, bankroll management
  5. Sentiment  — public sentiment, social/news flow
  6. Political  — regulatory and political landscape
  7. Contrarian — devil's advocate, contrarian case
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── Data models ───────────────────────────────────────────

@dataclass
class AgentOpinion:
    """Single agent's structured opinion on a debate topic."""
    agent_name: str
    stance: str          # 'strongly_bullish', 'bullish', 'neutral', 'bearish', 'strongly_bearish'
    confidence: float    # 0.0-1.0
    reasoning: str       # 1-3 sentence explanation
    key_factors: list[str] = field(default_factory=list)
    raw_response: str = ""


@dataclass
class CouncilVerdict:
    """Synthesized verdict from all 7 agents."""
    topic: str
    consensus: str       # 'strong_buy', 'buy', 'neutral', 'sell', 'strong_sell'
    confidence: float    # 0.0-1.0 overall confidence
    summary: str         # 2-4 sentence moderator synthesis
    bull_score: float    # 0.0-1.0 weighted bull votes
    bear_score: float    # 0.0-1.0 weighted bear votes
    agent_opinions: list[AgentOpinion] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    debate_id: int | None = None


# ── Agent definitions ─────────────────────────────────────

AGENT_DEFINITIONS = [
    {
        "name": "bull",
        "display": "Bull Agent",
        "role": (
            "You are the Bull Agent on a market analysis council. "
            "Your job is to identify positive catalysts, upside potential, "
            "and reasons why this bet or market position would be profitable. "
            "Be rigorous — only cite real, evidence-based bullish factors. "
            "Do not ignore obvious risks, but weight toward the upside case."
        ),
    },
    {
        "name": "bear",
        "display": "Bear Agent",
        "role": (
            "You are the Bear Agent on a market analysis council. "
            "Your job is to identify downside risks, negative catalysts, "
            "and reasons why this bet or market position would lose. "
            "Be rigorous — only cite real, evidence-based bearish factors. "
            "Do not ignore obvious upsides, but weight toward the downside case."
        ),
    },
    {
        "name": "indicator",
        "display": "Indicator Agent",
        "role": (
            "You are the Technical Indicator Agent on a market analysis council. "
            "Your job is to analyze trends, line movement, historical patterns, "
            "and statistical signals relevant to this question. "
            "Focus on data-driven insights: line movement, public vs sharp money, "
            "historical matchup trends, and model-based probability estimates."
        ),
    },
    {
        "name": "risk",
        "display": "Risk Agent",
        "role": (
            "You are the Risk Management Agent on a market analysis council. "
            "Your job is to evaluate risk/reward ratio, optimal stake sizing, "
            "portfolio exposure, and bankroll management considerations. "
            "Output should include suggested unit sizing (1-3 units) and whether "
            "the risk/reward justifies the position."
        ),
    },
    {
        "name": "sentiment",
        "display": "Sentiment Agent",
        "role": (
            "You are the Sentiment Agent on a market analysis council. "
            "Your job is to assess public sentiment, social media flow, news narratives, "
            "and crowd psychology around this topic. "
            "Identify whether the public is overweighting or underweighting certain factors, "
            "and how sentiment may create value or fade opportunities."
        ),
    },
    {
        "name": "political",
        "display": "Political Agent",
        "role": (
            "You are the Political Intelligence Agent on a market analysis council. "
            "Your job is to analyze regulatory environment, political risk, "
            "congressional activity, and government policy impacts on this topic. "
            "Consider upcoming legislation, regulatory changes, and how political "
            "dynamics could affect the market or outcome."
        ),
    },
    {
        "name": "contrarian",
        "display": "Contrarian Agent",
        "role": (
            "You are the Contrarian Agent on a market analysis council. "
            "Your job is to argue the opposite of conventional wisdom. "
            "If the consensus leans bullish, find the strongest bearish case. "
            "If the consensus leans bearish, find the strongest bullish case. "
            "Your goal is to expose blind spots and challenge groupthink."
        ),
    },
]

_STANCE_MAP = {
    "strongly_bullish": 1.0,
    "bullish": 0.6,
    "slightly_bullish": 0.3,
    "neutral": 0.0,
    "slightly_bearish": -0.3,
    "bearish": -0.6,
    "strongly_bearish": -1.0,
}

_VERDICT_THRESHOLDS = [
    (0.5, "strong_buy"),
    (0.2, "buy"),
    (-0.2, "neutral"),
    (-0.5, "sell"),
    (float("-inf"), "strong_sell"),
]


class CouncilAgent:
    """A single council agent that generates an opinion via LLM."""

    def __init__(self, definition: dict[str, str], inference) -> None:
        self._def = definition
        self._inference = inference

    @property
    def name(self) -> str:
        return self._def["name"]

    async def analyze(self, topic: str, context: str = "") -> AgentOpinion:
        """Generate a structured opinion on the topic.

        Args:
            topic: The question or market to analyze.
            context: Optional additional context (signals, politician data, odds).

        Returns:
            AgentOpinion with stance, confidence, reasoning, and key_factors.
        """
        context_block = f"\n\nAdditional context:\n{context}" if context else ""

        prompt = f"""Analyze the following market/betting question from your specialist perspective.

Topic: {topic}{context_block}

Respond in JSON format with exactly these fields:
{{
  "stance": "<one of: strongly_bullish, bullish, neutral, bearish, strongly_bearish>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<1-3 sentences explaining your position>",
  "key_factors": ["<factor 1>", "<factor 2>", "<factor 3>"]
}}

Reply with ONLY the JSON object, no other text."""

        try:
            result = await self._inference.generate(
                prompt=prompt,
                system=self._def["role"],
                force_provider="ollama",
                temperature=0.3,
            )
            raw = result.get("text", "").strip()

            # Parse JSON from response
            opinion_data = _parse_json_response(raw)
            stance = opinion_data.get("stance", "neutral")
            if stance not in _STANCE_MAP:
                stance = "neutral"

            return AgentOpinion(
                agent_name=self.name,
                stance=stance,
                confidence=float(opinion_data.get("confidence", 0.5)),
                reasoning=opinion_data.get("reasoning", ""),
                key_factors=opinion_data.get("key_factors", []),
                raw_response=raw,
            )

        except Exception as exc:
            logger.exception("CouncilAgent %s.analyze failed: %s", self.name, exc)
            return AgentOpinion(
                agent_name=self.name,
                stance="neutral",
                confidence=0.1,
                reasoning=f"Analysis unavailable: {exc}",
                key_factors=[],
                raw_response="",
            )


class Moderator:
    """Synthesizes opinions from all 7 agents into a final council verdict."""

    def __init__(self, inference) -> None:
        self._inference = inference

    async def synthesize(
        self,
        topic: str,
        opinions: list[AgentOpinion],
    ) -> CouncilVerdict:
        """Synthesize agent opinions into a final verdict.

        Computes weighted bull/bear scores, then calls LLM for a summary.

        Args:
            topic: The analyzed topic.
            opinions: List of 7 AgentOpinion instances.

        Returns:
            CouncilVerdict with consensus, scores, and summary.
        """
        # Compute weighted scores
        total_weight = 0.0
        weighted_sum = 0.0
        for op in opinions:
            weight = op.confidence
            stance_val = _STANCE_MAP.get(op.stance, 0.0)
            weighted_sum += stance_val * weight
            total_weight += weight

        if total_weight > 0:
            net_score = weighted_sum / total_weight
        else:
            net_score = 0.0

        # Map to bull/bear scores (0.0-1.0)
        bull_score = max(0.0, net_score)
        bear_score = max(0.0, -net_score)

        # Determine consensus
        consensus = "neutral"
        for threshold, verdict in _VERDICT_THRESHOLDS:
            if net_score >= threshold:
                consensus = verdict
                break

        # Overall confidence = average of individual confidences
        if opinions:
            overall_confidence = sum(op.confidence for op in opinions) / len(opinions)
        else:
            overall_confidence = 0.0

        # Build opinions summary for LLM
        opinions_text = "\n".join([
            f"- {op.agent_name.upper()} ({op.stance}, {op.confidence:.0%}): {op.reasoning}"
            for op in opinions
        ])

        # LLM summary synthesis
        try:
            prompt = f"""You are moderating a council of AI analysts who have evaluated the following question:

Topic: {topic}

Agent opinions:
{opinions_text}

Net consensus signal: {consensus.upper()} (bull_score={bull_score:.2f}, bear_score={bear_score:.2f})

Write a 2-4 sentence synthesis that:
1. States the overall verdict clearly
2. Highlights the strongest supporting argument
3. Notes the key risk or counterargument
4. Gives a practical recommendation

Be direct and concrete. No hedging. No vague language."""

            result = await self._inference.generate(
                prompt=prompt,
                system=(
                    "You are an expert market moderator synthesizing a multi-agent council analysis. "
                    "Be direct, specific, and actionable. No filler words."
                ),
                force_provider="ollama",
                temperature=0.2,
            )
            summary = result.get("text", "").strip()
        except Exception as exc:
            logger.warning("Moderator.synthesize LLM failed: %s", exc)
            summary = (
                f"Council verdict: {consensus.upper()} with {overall_confidence:.0%} confidence. "
                f"Bull score: {bull_score:.2f}, Bear score: {bear_score:.2f}."
            )

        return CouncilVerdict(
            topic=topic,
            consensus=consensus,
            confidence=round(overall_confidence, 3),
            summary=summary,
            bull_score=round(bull_score, 3),
            bear_score=round(bear_score, 3),
            agent_opinions=opinions,
        )


# ── Helpers ───────────────────────────────────────────────

def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract and parse a JSON object from LLM response text."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from response: %r", text[:200])
    return {}
