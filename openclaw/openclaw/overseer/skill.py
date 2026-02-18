"""OverseerSkill: integrates the Overseer agents into the OpenClaw skill system.

This skill acts as the user-facing interface for the Overseer.
It delegates commands to OverseerAgent (Agent 1), which in turn
controls SecurityProtocolAgent (Agent 2).
"""

from __future__ import annotations

import logging
from typing import ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.inference.router import InferenceRouter
from openclaw.memory.store import MemoryStore
from openclaw.overseer.config import OverseerConfig
from openclaw.overseer.overseer_agent import OverseerAgent
from openclaw.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class OverseerSkill(BaseSkill):
    """Skill interface for the OpenClaw Overseer system.

    Routes user messages to Agent 1 (OverseerAgent), which handles
    the human-in-the-loop workflow and controls Agent 2.
    """

    name: ClassVar[str] = "overseer"
    description: ClassVar[str] = (
        "Security overseer: manage security agents, run audits, "
        "approve policy changes, view security reports"
    )
    min_tier: ClassVar[int] = 3
    examples: ClassVar[list[str]] = [
        "overseer status",
        "overseer audit",
        "overseer last report",
        "overseer start agent",
        "overseer stop agent",
        "overseer pending",
    ]

    def __init__(self, store: MemoryStore, inference: InferenceRouter):
        super().__init__(store, inference)
        config = OverseerConfig()
        self._overseer = OverseerAgent(config, store, inference)

    @property
    def overseer(self) -> OverseerAgent:
        """Access the overseer agent (used by main.py to wire up scheduler)."""
        return self._overseer

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        try:
            result = await self._overseer.handle_command(
                text=ctx.message.content,
                sender_id=ctx.message.sender_id,
            )
            return self._reply(result)
        except Exception as exc:
            logger.exception("Overseer command failed")
            return self._error(f"Overseer error: {exc}")

    async def can_handle(self, text: str) -> float:
        text_lower = text.lower()
        if "overseer" in text_lower:
            return 0.95
        if "keyvault" in text_lower or "key vault" in text_lower:
            return 0.95
        if any(
            phrase in text_lower
            for phrase in [
                "security audit",
                "security agent",
                "security protocol",
                "run audit",
                "agent status",
                "pending approval",
                "api key",
                "api keys",
            ]
        ):
            return 0.85
        return 0.0
