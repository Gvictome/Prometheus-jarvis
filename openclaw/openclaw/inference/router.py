"""Inference router: scores complexity and routes to local or cloud LLM.

Architecture:
  - Athena (user-facing conversation): OpenRouter (Gemma 3 27B) — free tier
  - Subagent work (skills, analysis, etc.): Ollama (qwen2.5:3b) — local
  - Per-agent routing: agents.json maps sender IDs to named agents with
    primary + fallback model lists (all via OpenRouter).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from openclaw.config import settings
from openclaw.inference.openrouter_client import OpenRouterClient
from openclaw.inference.cost_tracker import CostTracker
from openclaw.inference.ollama_client import OllamaClient
from openclaw.memory.store import MemoryStore
import openclaw.agent_config as agent_config

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
    """Routes inference requests to Ollama (local) or OpenRouter (cloud).

    Routing strategy:
      - force_provider="openrouter" → Gemma 3 27B via OpenRouter (Athena conversations)
      - force_provider="ollama"     → qwen2.5:3b local (subagent/skill work)
      - None (auto)                 → complexity score decides
    """

    def __init__(self, store: MemoryStore):
        self.ollama = OllamaClient()
        self.openrouter = OpenRouterClient()
        self.cost_tracker = CostTracker(store)
        self.threshold = settings.COMPLEXITY_THRESHOLD

    async def chat(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        force_provider: str | None = None,
        temperature: float = 0.7,
        sender_id: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Route chat to the appropriate provider.

        If ``sender_id`` is provided the agent config is consulted first.
        The resolved agent's primary model is tried via OpenRouter; on
        failure each fallback model is tried in order before falling back
        to the standard provider-selection logic.

        Args:
            messages: Chat messages [{"role": "user", "content": "..."}]
            system: System prompt
            force_provider: "ollama" or "openrouter" to bypass routing
            temperature: Sampling temperature
            sender_id: Originating sender identifier used for agent routing
        """
        # ── Agent-based routing ───────────────────────────
        if sender_id and not force_provider:
            agent_name = agent_config.resolve_agent(sender_id)
            if agent_name:
                model_cfg = agent_config.get_model_config(agent_name)
                if model_cfg:
                    result = await self._try_openrouter_with_fallbacks(
                        messages=messages,
                        system=system,
                        temperature=temperature,
                        primary=model_cfg["primary"],
                        fallbacks=model_cfg["fallbacks"],
                        agent_name=agent_name,
                        tools=tools,
                    )
                    if result is not None:
                        self.cost_tracker.record(result)
                        return result
                    # All agent models failed — fall through to standard routing
                    logger.warning(
                        "All agent models for %s failed, falling back to standard routing",
                        agent_name,
                    )

        # ── Standard provider routing ─────────────────────
        last_user_msg = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                last_user_msg = msg["content"]
                break

        provider = force_provider or self._select_provider(last_user_msg)

        # Normalize legacy "claude" references
        if provider == "claude":
            provider = "openrouter"

        try:
            if provider == "openrouter":
                if not self.openrouter.is_available():
                    logger.warning("OpenRouter unavailable, falling back to Ollama")
                    provider = "ollama"

            if provider == "openrouter":
                result = await self.openrouter.chat(
                    messages, system=system, temperature=temperature, tools=tools
                )
            else:
                result = await self.ollama.chat(
                    messages, system=system, temperature=temperature
                )

            self.cost_tracker.record(result)
            return result

        except Exception as e:
            logger.exception("Primary provider %s failed", provider)
            # Fallback to the other provider
            fallback = "ollama" if provider == "openrouter" else "openrouter"
            if fallback == "openrouter" and not self.openrouter.is_available():
                raise

            logger.info("Falling back to %s", fallback)
            if fallback == "openrouter":
                result = await self.openrouter.chat(
                    messages, system=system, temperature=temperature, tools=tools
                )
            else:
                result = await self.ollama.chat(
                    messages, system=system, temperature=temperature
                )

            self.cost_tracker.record(result)
            return result

    async def _try_openrouter_with_fallbacks(
        self,
        messages: list[dict[str, str]],
        system: str | None,
        temperature: float,
        primary: str,
        fallbacks: list[str],
        agent_name: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Try the primary model then each fallback in order via OpenRouter.

        Returns the first successful result, or ``None`` if all models fail.

        Args:
            messages: Chat messages to send.
            system: Optional system prompt.
            temperature: Sampling temperature.
            primary: Primary model ID (bare, no ``openrouter/`` prefix).
            fallbacks: Ordered list of fallback model IDs.
            agent_name: Agent name used only for log messages.
        """
        if not self.openrouter.is_available():
            logger.warning("OpenRouter unavailable, skipping agent model routing")
            return None

        models_to_try = [primary] + fallbacks
        for model in models_to_try:
            try:
                logger.debug("Agent %s: trying model %s", agent_name, model)
                # Create a temporary client scoped to this model
                client = OpenRouterClient(
                    api_key=self.openrouter.api_key,
                    model=model,
                )
                result = await client.chat(
                    messages, system=system, temperature=temperature, tools=tools
                )
                logger.info("Agent %s: succeeded with model %s", agent_name, model)
                return result
            except Exception:
                logger.warning(
                    "Agent %s: model %s failed, trying next", agent_name, model
                )

        return None

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        force_provider: str | None = None,
        temperature: float = 0.7,
        sender_id: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Single-turn generation.

        Args:
            prompt: The user prompt.
            system: Optional system prompt.
            force_provider: "ollama" or "openrouter" to bypass auto-routing.
            temperature: Sampling temperature.
            sender_id: Originating sender identifier used for agent routing.
            tools: Optional OpenAI-compatible tool schemas for function calling.
        """
        return await self.chat(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            force_provider=force_provider,
            temperature=temperature,
            sender_id=sender_id,
            tools=tools,
        )

    def _select_provider(self, text: str) -> str:
        score = score_complexity(text)
        provider = "openrouter" if score >= self.threshold else "ollama"
        logger.debug(
            "Complexity score: %.2f -> %s (threshold: %.2f)",
            score,
            provider,
            self.threshold,
        )
        return provider
