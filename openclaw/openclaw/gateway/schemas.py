"""Unified message schemas for the OpenClaw gateway."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Channel(str, Enum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    API = "api"
    SCHEDULER = "scheduler"


class MessageType(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    COMMAND = "command"


class UnifiedMessage(BaseModel):
    """Normalized message from any channel."""
    channel: Channel
    sender_id: str
    content: str
    message_type: MessageType = MessageType.TEXT
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    conversation_id: str | None = None
    reply_to: str | None = None

    # Populated by voice-gateway when message_type == VOICE
    audio_url: str | None = None
    audio_duration: float | None = None


class SkillMatch(BaseModel):
    """Result of intent classification."""
    skill_name: str
    confidence: float = 1.0
    entities: dict[str, Any] = Field(default_factory=dict)
    raw_intent: str | None = None


class SkillContext(BaseModel):
    """Context passed to skill execution."""
    message: UnifiedMessage
    match: SkillMatch
    user_tier: int = 0
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    memories: list[str] = Field(default_factory=list)


class SkillResponse(BaseModel):
    """Response from a skill execution."""
    text: str
    channel: Channel | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    audio_url: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class HealthStatus(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    services: dict[str, str] = Field(default_factory=dict)
