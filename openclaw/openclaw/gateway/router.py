"""Gateway router: full message pipeline from intake to response."""

from __future__ import annotations

import logging

from openclaw.gateway.intent import classify_intent, classify_with_llm
from openclaw.gateway.middleware import AuthMiddleware, RateLimiter
from openclaw.gateway.schemas import (
    SkillContext,
    SkillResponse,
    UnifiedMessage,
)
from openclaw.inference.router import InferenceRouter
from openclaw.memory.context import build_conversation_id, get_context_for_message
from openclaw.memory.store import MemoryStore
from openclaw.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class GatewayRouter:
    """Orchestrates the full message pipeline."""

    def __init__(
        self,
        store: MemoryStore,
        inference: InferenceRouter,
        registry: SkillRegistry,
    ):
        self.store = store
        self.inference = inference
        self.registry = registry
        self.auth = AuthMiddleware(store)
        self.rate_limiter = RateLimiter()

    async def handle_message(self, message: UnifiedMessage) -> SkillResponse:
        """Process a message through the full pipeline.

        Flow: Auth -> Rate Limit -> Context -> Intent -> Skill -> Persist -> Respond
        """
        sender = message.sender_id
        channel = message.channel.value

        # ── Rate Limiting ────────────────────────────────
        if not self.rate_limiter.check(sender):
            return SkillResponse(
                text="You're sending messages too fast. Please slow down.",
                error="rate_limited",
            )

        # ── Conversation Context ─────────────────────────
        conv_id = message.conversation_id or build_conversation_id(channel, sender)
        self.store.get_or_create_conversation(conv_id, channel, sender)

        context = await get_context_for_message(
            store=self.store,
            conversation_id=conv_id,
            sender_id=sender,
            query=message.content,
        )

        # ── Intent Classification ────────────────────────
        intent = classify_intent(
            message.content,
            available_skills=self.registry.skill_names,
        )

        # If low confidence, try skill self-matching
        if intent.confidence < 0.7:
            skill_match = await self.registry.find_best_match(message.content)
            if skill_match and skill_match.confidence > intent.confidence:
                intent = skill_match

        # If still low, try LLM classification
        if intent.confidence < 0.5:
            intent = await classify_with_llm(
                message.content,
                self.registry.skill_descriptions,
                self.inference,
            )

        logger.info(
            "Intent: %s (%.2f) for message from %s/%s",
            intent.skill_name,
            intent.confidence,
            channel,
            sender,
        )

        # ── Skill Execution ──────────────────────────────
        skill = self.registry.get(intent.skill_name)
        if skill is None:
            skill = self.registry.get("conversation")

        # Auth check
        user_tier = self.auth.get_user_tier(sender)
        if user_tier < skill.min_tier:
            return SkillResponse(
                text=f"Sorry, you need tier {skill.min_tier} access for this action.",
                error="insufficient_tier",
            )

        # Build skill context
        skill_ctx = SkillContext(
            message=message,
            match=intent,
            user_tier=user_tier,
            conversation_history=context["conversation_history"],
            memories=context["memories"],
        )

        try:
            response = await skill.execute(skill_ctx)
        except Exception as e:
            logger.exception("Skill %s failed", intent.skill_name)
            response = SkillResponse(
                text="Sorry, something went wrong processing your request.",
                error=str(e),
            )

        # ── Persist Messages ─────────────────────────────
        self.store.add_message(conv_id, "user", message.content, channel)
        self.store.add_message(conv_id, "assistant", response.text, channel)

        # ── Audit Log ────────────────────────────────────
        self.store.log_audit(
            user_id=sender,
            action=f"skill:{intent.skill_name}",
            detail=message.content[:200],
            tier=user_tier,
        )

        return response
