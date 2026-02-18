"""Base skill abstract class and skill context."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.inference.router import InferenceRouter
from openclaw.memory.store import MemoryStore

if TYPE_CHECKING:
    from openclaw.skills.registry import SkillRegistry

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
        # Populated by SkillRegistry.register() to enable cross-skill tool dispatch
        self.registry: SkillRegistry | None = None

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

    @classmethod
    def get_tool_schema(cls) -> dict[str, Any] | None:
        """Return an OpenAI-compatible tool schema, or None if not tool-callable.

        Override in subclasses that support function/tool calling.
        """
        return None

    async def execute_tool(self, action: str, **kwargs: Any) -> str:
        """Execute a specific action from a tool call and return plain text.

        Override in subclasses that implement ``get_tool_schema()``.
        """
        raise NotImplementedError(f"{self.name} does not support tool calling")

    def _error(self, msg: str) -> SkillResponse:
        """Helper to create error responses."""
        return SkillResponse(text=msg, error=msg)

    def _reply(self, text: str, **kwargs) -> SkillResponse:
        """Helper to create success responses."""
        return SkillResponse(text=text, **kwargs)
