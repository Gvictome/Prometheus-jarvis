"""OpenClaw — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from openclaw.config import settings
from openclaw.gateway.router import GatewayRouter
from openclaw.gateway.schemas import (
    Channel,
    HealthStatus,
    MessageType,
    SkillResponse,
    UnifiedMessage,
)
from openclaw.inference.router import InferenceRouter
from openclaw.memory.store import MemoryStore
from openclaw.skills.conversation import ConversationSkill
from openclaw.skills.registry import SkillRegistry

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Global state (initialized in lifespan) ───────────────
store: MemoryStore | None = None
gateway: GatewayRouter | None = None


def _register_skills(registry: SkillRegistry):
    """Register all available skills."""
    registry.register(ConversationSkill)

    # Import and register optional skills (fail gracefully)
    try:
        from openclaw.skills.system_admin import SystemAdminSkill
        registry.register(SystemAdminSkill)
    except ImportError:
        logger.debug("system_admin skill not available")

    try:
        from openclaw.skills.daily_briefing import DailyBriefingSkill
        registry.register(DailyBriefingSkill)
    except ImportError:
        logger.debug("daily_briefing skill not available")

    try:
        from openclaw.skills.web_search import WebSearchSkill
        registry.register(WebSearchSkill)
    except ImportError:
        logger.debug("web_search skill not available")

    try:
        from openclaw.skills.smart_home import SmartHomeSkill
        registry.register(SmartHomeSkill)
    except ImportError:
        logger.debug("smart_home skill not available")

    try:
        from openclaw.skills.security_monitor import SecurityMonitorSkill
        registry.register(SecurityMonitorSkill)
    except ImportError:
        logger.debug("security_monitor skill not available")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, gateway

    logger.info("Starting OpenClaw...")
    store = MemoryStore()
    inference = InferenceRouter(store)
    registry = SkillRegistry(store, inference)
    _register_skills(registry)
    gateway = GatewayRouter(store, inference, registry)
    logger.info("OpenClaw ready. Skills: %s", registry.skill_names)

    yield

    logger.info("Shutting down OpenClaw...")
    if store:
        store.close()


app = FastAPI(
    title="OpenClaw",
    description="Jarvis AI Assistant — Core Gateway",
    version="0.1.0",
    lifespan=lifespan,
)


# ── API Models ───────────────────────────────────────────

class MessageRequest(BaseModel):
    channel: str = "api"
    sender_id: str = "anonymous"
    content: str
    message_type: str = "text"
    conversation_id: str | None = None
    metadata: dict | None = None


class MessageResponse(BaseModel):
    text: str
    metadata: dict | None = None
    error: str | None = None


# ── Endpoints ────────────────────────────────────────────

@app.post("/api/v1/message", response_model=MessageResponse)
async def handle_message(req: MessageRequest):
    """Process a message through the OpenClaw pipeline."""
    if not gateway:
        raise HTTPException(status_code=503, detail="Service not ready")

    # Normalize channel
    try:
        channel = Channel(req.channel)
    except ValueError:
        channel = Channel.API

    message = UnifiedMessage(
        channel=channel,
        sender_id=req.sender_id,
        content=req.content,
        message_type=MessageType(req.message_type) if req.message_type else MessageType.TEXT,
        conversation_id=req.conversation_id,
        metadata=req.metadata or {},
    )

    response: SkillResponse = await gateway.handle_message(message)

    return MessageResponse(
        text=response.text,
        metadata=response.metadata,
        error=response.error,
    )


@app.get("/health", response_model=HealthStatus)
async def health():
    """Health check endpoint."""
    services = {}

    # Check Ollama
    if gateway:
        try:
            healthy = await gateway.inference.ollama.is_healthy()
            services["ollama"] = "ok" if healthy else "down"
        except Exception:
            services["ollama"] = "error"

        # Check Claude availability
        services["claude"] = "ok" if gateway.inference.claude.is_available() else "unconfigured"

        # Budget status
        budget = gateway.inference.cost_tracker.get_budget_status()
        services["budget"] = f"${budget['spent_usd']}/{budget['budget_usd']}"

    return HealthStatus(services=services)


@app.get("/api/v1/skills")
async def list_skills():
    """List all registered skills."""
    if not gateway:
        raise HTTPException(status_code=503, detail="Service not ready")
    return gateway.registry.list_skills()
