"""Default conversation skill — LLM passthrough for general chat."""

from __future__ import annotations

import logging
from typing import ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Jarvis, a highly capable AI personal assistant. You are helpful, \
concise, and proactive. You speak naturally and adapt your tone to the context — professional \
when needed, casual when appropriate.

Key traits:
- Direct and efficient in responses
- Proactively suggest actions when relevant
- Remember context from the conversation
- Admit when you don't know something
- Keep responses concise unless detail is requested

{memory_context}"""


class ConversationSkill(BaseSkill):
    name: ClassVar[str] = "conversation"
    description: ClassVar[str] = "General conversation and questions"
    min_tier: ClassVar[int] = 0
    examples: ClassVar[list[str]] = [
        "Hello",
        "What do you think about...",
        "Help me brainstorm...",
    ]

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        # Build memory context section
        memory_section = ""
        if ctx.memories:
            memory_lines = "\n".join(f"- {m}" for m in ctx.memories)
            memory_section = (
                f"\nRelevant things you remember about this user:\n{memory_lines}"
            )

        system = SYSTEM_PROMPT.format(memory_context=memory_section)

        # Build chat messages from history + current message
        messages = []
        for msg in ctx.conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": ctx.message.content})

        try:
            result = await self.inference.chat(
                messages=messages,
                system=system,
            )
            return self._reply(
                result["text"],
                metadata={
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                },
            )
        except Exception as e:
            logger.exception("Conversation inference failed")
            return self._error(f"Sorry, I'm having trouble thinking right now: {e}")

    async def can_handle(self, text: str) -> float:
        # Conversation is the fallback — always returns a baseline confidence
        return 0.1
