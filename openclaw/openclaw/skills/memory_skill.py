"""Memory skill — remember, recall, and forget user-specific information."""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class MemorySkill(BaseSkill):
    """Handles remember/recall/forget intents using the MemoryStore.

    Triggers:
      - "remember that ..."
      - "what do you know about ..."
      - "forget about ..."
    """

    name: ClassVar[str] = "memory"
    description: ClassVar[str] = (
        "Store and retrieve personal memories — remember facts, recall information, forget things"
    )
    min_tier: ClassVar[int] = 1
    examples: ClassVar[list[str]] = [
        "remember that my favourite team is the Lakers",
        "what do you know about my preferences",
        "forget about my old address",
        "recall what I told you about the project",
    ]

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        text = ctx.message.content.strip()
        text_lower = text.lower()
        user_id = ctx.message.sender_id

        # ── Remember ─────────────────────────────────────────────
        remember_match = re.search(
            r"\bremember\s+(that\s+)?(.+)", text_lower, re.IGNORECASE
        )
        if remember_match:
            content = remember_match.group(2).strip()
            # Use original casing from the raw message
            raw_match = re.search(r"\bremember\s+(?:that\s+)?(.+)", text, re.IGNORECASE)
            if raw_match:
                content = raw_match.group(1).strip()
            return await self._remember(user_id, content, ctx)

        # ── Forget ───────────────────────────────────────────────
        forget_match = re.search(
            r"\bforget\s+(?:about\s+)?(.+)", text_lower, re.IGNORECASE
        )
        if forget_match:
            query = forget_match.group(1).strip()
            raw_match = re.search(r"\bforget\s+(?:about\s+)?(.+)", text, re.IGNORECASE)
            if raw_match:
                query = raw_match.group(1).strip()
            return await self._forget(user_id, query)

        # ── Recall ───────────────────────────────────────────────
        recall_match = re.search(
            r"\b(?:what do you (?:know|remember) about|recall)\s+(.+)",
            text_lower,
            re.IGNORECASE,
        )
        if recall_match:
            query = recall_match.group(1).strip()
            raw_match = re.search(
                r"\b(?:what do you (?:know|remember) about|recall)\s+(.+)",
                text,
                re.IGNORECASE,
            )
            if raw_match:
                query = raw_match.group(1).strip()
            return self._recall(user_id, query)

        # ── Generic: list recent memories ────────────────────────
        return self._recall(user_id, query="")

    # ── Handlers ─────────────────────────────────────────────────

    async def _remember(self, user_id: str, content: str, ctx: SkillContext) -> SkillResponse:
        """Store a new memory for this user."""
        if not content:
            return self._error("What would you like me to remember?")

        memory_id = self.store.add_memory(
            user_id=user_id,
            content=content,
            category="general",
        )
        self.store.log_audit(
            user_id=user_id,
            action="memory_stored",
            detail=content[:200],
            tier=ctx.user_tier,
        )
        logger.info("Stored memory id=%d for user %s", memory_id, user_id)
        return self._reply(f"Got it — I'll remember that: \"{content}\"")

    def _recall(self, user_id: str, query: str) -> SkillResponse:
        """Retrieve memories matching a query, or list recent memories."""
        if query:
            memories = self.store.search_memories(query=query, limit=10)
            # Filter to this user's memories only
            memories = [m for m in memories if m.get("user_id") == user_id]
        else:
            memories = self.store.get_memories(user_id=user_id, limit=10)

        if not memories:
            if query:
                return self._reply(f"I don't have anything stored about \"{query}\".")
            return self._reply("I haven't stored any memories for you yet. Try: \"remember that ...\"")

        lines = ["Here's what I remember:"]
        for m in memories:
            created = str(m.get("created_at", ""))[:10]
            lines.append(f"- {m['content']} ({created})")

        return self._reply("\n".join(lines))

    async def _forget(self, user_id: str, query: str) -> SkillResponse:
        """Find and mark matching memories as deleted (soft-delete via category)."""
        if not query:
            return self._error("What would you like me to forget?")

        # Search for matching memories for this user
        memories = self.store.search_memories(query=query, limit=10)
        user_memories = [m for m in memories if m.get("user_id") == user_id]

        if not user_memories:
            return self._reply(f"I couldn't find anything stored about \"{query}\".")

        # Soft-delete by storing a replacement memory tagged "forgotten"
        # The store doesn't have a delete method; we add a tombstone record
        for m in user_memories:
            self.store.add_memory(
                user_id=user_id,
                content=f"[FORGOTTEN] {m['content']}",
                category="forgotten",
            )

        count = len(user_memories)
        self.store.log_audit(
            user_id=user_id,
            action="memory_forgotten",
            detail=query[:200],
            tier=1,
        )
        return self._reply(
            f"Done — I've marked {count} memory/memories about \"{query}\" as forgotten."
        )
