"""Skill discovery and lookup registry."""

from __future__ import annotations

import json
import logging
from typing import Any

from openclaw.gateway.schemas import SkillMatch
from openclaw.inference.router import InferenceRouter
from openclaw.memory.store import MemoryStore
from openclaw.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Manages skill registration and lookup."""

    def __init__(self, store: MemoryStore, inference: InferenceRouter):
        self.store = store
        self.inference = inference
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill_class: type[BaseSkill]) -> BaseSkill:
        """Instantiate and register a skill class."""
        instance = skill_class(store=self.store, inference=self.inference)
        instance.registry = self  # back-reference for cross-skill tool dispatch
        self._skills[instance.name] = instance
        logger.info("Registered skill: %s", instance.name)
        return instance

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def list_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "min_tier": s.min_tier,
                "examples": s.examples,
            }
            for s in self._skills.values()
        ]

    async def find_best_match(self, text: str) -> SkillMatch | None:
        """Ask each skill if it can handle the text.

        Returns the highest-confidence match above 0.5 threshold.
        This is used as a secondary check after the intent classifier.
        """
        best: SkillMatch | None = None
        best_score = 0.5

        for skill in self._skills.values():
            try:
                confidence = await skill.can_handle(text)
                if confidence > best_score:
                    best_score = confidence
                    best = SkillMatch(
                        skill_name=skill.name,
                        confidence=confidence,
                    )
            except Exception:
                logger.exception("Error in %s.can_handle", skill.name)

        return best

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool schemas for all tool-callable skills."""
        schemas = []
        for skill in self._skills.values():
            schema = skill.__class__.get_tool_schema()
            if schema is not None:
                schemas.append(schema)
        return schemas

    async def dispatch_tool_call(
        self,
        tool_name: str,
        args_json: str | dict[str, Any],
        user_tier: int = 0,
    ) -> str:
        """Execute a skill tool call and return the plain text result."""
        skill = self.get(tool_name)
        if skill is None:
            return f"Tool '{tool_name}' not found."
        if user_tier < skill.min_tier:
            return f"Insufficient access tier for tool '{tool_name}'."
        try:
            kwargs: dict[str, Any] = (
                json.loads(args_json) if isinstance(args_json, str) else dict(args_json)
            )
            action = kwargs.pop("action", "")
            return await skill.execute_tool(action, **kwargs)
        except NotImplementedError:
            return f"Skill '{tool_name}' does not support tool calling."
        except Exception as exc:
            logger.exception("Tool call dispatch failed for %s", tool_name)
            return f"Error executing {tool_name}: {exc}"

    @property
    def skill_names(self) -> list[str]:
        return list(self._skills.keys())

    @property
    def skill_descriptions(self) -> str:
        """Format skill list for LLM context."""
        lines = []
        for s in self._skills.values():
            examples = ", ".join(f'"{e}"' for e in s.examples[:3])
            lines.append(f"- {s.name}: {s.description} (e.g. {examples})")
        return "\n".join(lines)
