"""Base skill abstract class and skill context."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.inference.router import InferenceRouter
from openclaw.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class BaseSkill(ABC):
    """Abstract base class for all OpenClaw skills."""

    # Subclasses must set these
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    min_tier: ClassVar[int] = 0  # Minimum user tier required
    examples: ClassVar[list[str]] = []  # Example trigger phrases

    def __init__(self, store: MemoryStore, inference: InferenceRouter):
        self.store = store
        self.inference = inference

    @abstractmethod
    async def execute(self, ctx: SkillContext) -> SkillResponse:
        """Execute the skill with given context. Must be implemented by subclasses."""
        ...

    async def can_handle(self, text: str) -> float:
        """Return confidence 0.0-1.0 that this skill can handle the text.

        Override for custom matching beyond the registry's intent classifier.
        Default returns 0.0 (rely on intent classifier).
        """
        return 0.0

    def _error(self, msg: str) -> SkillResponse:
        """Helper to create error responses."""
        return SkillResponse(text=msg, error=msg)

    def _reply(self, text: str, **kwargs) -> SkillResponse:
        """Helper to create success responses."""
        return SkillResponse(text=text, **kwargs)
