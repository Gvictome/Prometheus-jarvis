"""Inference router: scores complexity and routes to local or cloud LLM."""

from __future__ import annotations

import logging
import re
from typing import Any

from openclaw.config import settings
from openclaw.inference.claude_client import ClaudeClient
from openclaw.inference.cost_tracker import CostTracker
from openclaw.inference.ollama_client import OllamaClient
from openclaw.memory.store import MemoryStore

logger = logging.getLogger(__name__)

# Heuristics for complexity scoring
_COMPLEX_INDICATORS = [
    (r"\b(analyze|explain|compare|summarize|write.*code|debug|refactor)\b", 0.3),
    (r"\b(multi.?step|complex|detailed|comprehensive)\b", 0.2),
    (r"```", 0.3),  # Code blocks suggest technical content
    (r"\b(why|how does|what if)\b", 0.15),
]

_SIMPLE_INDICATORS = [
    (r"^(hi|hello|hey|thanks|ok|yes|no|sure)\b", -0.4),
    (r"^(what time|what day|what date)\b", -0.3),
    (r"\b(turn on|turn off|set|toggle)\b", -0.2),
]


def score_complexity(text: str) -> float:
    """Score message complexity 0.0 (simple) to 1.0 (complex)."""
    score = 0.5  # neutral baseline
    text_lower = text.lower().strip()

    # Length factor
    word_count = len(text_lower.split())
    if word_count > 100:
        score += 0.2
    elif word_count < 10:
        score -= 0.15

    for pattern, weight in _COMPLEX_INDICATORS:
        if re.search(pattern, text_lower):
            score += weight

    for pattern, weight in _SIMPLE_INDICATORS:
        if re.search(pattern, text_lower):
            score += weight  # weight is negative

    return max(0.0, min(1.0, score))


class InferenceRouter:
    """Routes inference requests to Ollama (local) or Claude (cloud)."""

    def __init__(self, store: MemoryStore):
        self.ollama = OllamaClient()
        self.claude = ClaudeClient()
        self.cost_tracker = CostTracker(store)
        self.threshold = settings.COMPLEXITY_THRESHOLD

    async def chat(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        force_provider: str | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Route chat to the appropriate provider.

        Args:
            messages: Chat messages [{"role": "user", "content": "..."}]
            system: System prompt
            force_provider: "ollama" or "claude" to bypass routing
            temperature: Sampling temperature
        """
        # Determine provider
        last_user_msg = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                last_user_msg = msg["content"]
                break

        provider = force_provider or self._select_provider(last_user_msg)

        try:
            if provider == "claude":
                if not self.claude.is_available():
                    logger.warning("Claude unavailable, falling back to Ollama")
                    provider = "ollama"
                elif not self.cost_tracker.is_within_budget():
                    logger.warning("Monthly budget exceeded, falling back to Ollama")
                    provider = "ollama"

            if provider == "claude":
                result = await self.claude.chat(
                    messages, system=system, temperature=temperature
                )
            else:
                result = await self.ollama.chat(
                    messages, system=system, temperature=temperature
                )

            # Track cost for cloud calls
            self.cost_tracker.record(result)
            return result

        except Exception as e:
            logger.exception("Primary provider %s failed", provider)
            # Fallback to the other provider
            fallback = "ollama" if provider == "claude" else "claude"
            if fallback == "claude" and not self.claude.is_available():
                raise

            logger.info("Falling back to %s", fallback)
            if fallback == "claude":
                result = await self.claude.chat(
                    messages, system=system, temperature=temperature
                )
            else:
                result = await self.ollama.chat(
                    messages, system=system, temperature=temperature
                )

            self.cost_tracker.record(result)
            return result

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        force_provider: str | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Single-turn generation."""
        return await self.chat(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            force_provider=force_provider,
            temperature=temperature,
        )

    def _select_provider(self, text: str) -> str:
        score = score_complexity(text)
        provider = "claude" if score >= self.threshold else "ollama"
        logger.debug(
            "Complexity score: %.2f -> %s (threshold: %.2f)",
            score,
            provider,
            self.threshold,
        )
        return provider
