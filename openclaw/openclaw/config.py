"""Environment-based configuration for OpenClaw."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _env(key: str, default: Any = None, cast: type = str) -> Any:
    val = os.getenv(key, default)
    if val is None:
        return None
    if cast is bool:
        return str(val).lower() in ("1", "true", "yes")
    return cast(val)


class Settings:
    # ── Core ──────────────────────────────────────────────
    SECRET_KEY: str = _env("OPENCLAW_SECRET_KEY", "dev-secret")
    LOG_LEVEL: str = _env("OPENCLAW_LOG_LEVEL", "INFO")
    DATA_DIR: Path = Path(_env("DATA_DIR", "/data"))
    DB_PATH: Path = Path(_env("DB_PATH", "/data/openclaw.db"))

    # ── Ollama (local inference) ──────────────────────────
    OLLAMA_BASE_URL: str = _env("OLLAMA_BASE_URL", "http://ollama:11434")
    OLLAMA_MODEL: str = _env("OLLAMA_MODEL", "qwen2.5:3b")
    OLLAMA_EMBED_MODEL: str = _env("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # ── OpenRouter (cloud inference — Athena) ───────────────
    OPENROUTER_API_KEY: str | None = _env("OPENROUTER_API_KEY")
    OPENROUTER_MODEL: str = _env("OPENROUTER_MODEL", "google/gemma-3-27b-it:free")
    OPENROUTER_MAX_TOKENS: int = _env("OPENROUTER_MAX_TOKENS", 4096, int)

    # ── Claude (legacy / fallback) ────────────────────────
    ANTHROPIC_API_KEY: str | None = _env("ANTHROPIC_API_KEY")
    CLAUDE_MODEL: str = _env("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    CLAUDE_MAX_TOKENS: int = _env("CLAUDE_MAX_TOKENS", 4096, int)

    # ── Inference Router ─────────────────────────────────
    COMPLEXITY_THRESHOLD: float = _env("INFERENCE_COMPLEXITY_THRESHOLD", 0.6, float)
    MONTHLY_BUDGET_USD: float = _env("INFERENCE_MONTHLY_BUDGET_USD", 50.0, float)

    # ── Channels ─────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str | None = _env("TELEGRAM_BOT_TOKEN")
    WHATSAPP_BRIDGE_URL: str = _env("WHATSAPP_BRIDGE_URL", "http://whatsapp-bridge:3001")

    # ── Voice ────────────────────────────────────────────
    VOICE_GATEWAY_URL: str = _env("VOICE_GATEWAY_URL", "http://voice-gateway:8001")
    WHISPER_MODEL: str = _env("WHISPER_MODEL", "base")

    # ── External Services ────────────────────────────────
    NOTION_TOKEN: str | None = _env("NOTION_TOKEN")
    NOTION_CALENDAR_DB: str | None = _env("NOTION_CALENDAR_DB")
    NOTION_TASKS_DB: str | None = _env("NOTION_TASKS_DB")
    NOTION_PROJECTS_DB: str | None = _env("NOTION_PROJECTS_DB")
    NOTION_NOTES_DB: str | None = _env("NOTION_NOTES_DB")
    NOTION_DAILY_PARENT_PAGE: str | None = _env("NOTION_DAILY_PARENT_PAGE")

    GOOGLE_DRIVE_CREDENTIALS_JSON: str | None = _env("GOOGLE_DRIVE_CREDENTIALS_JSON")
    GOOGLE_DRIVE_DEFAULT_PARENT_ID: str | None = _env("GOOGLE_DRIVE_DEFAULT_PARENT_ID")

    HOME_ASSISTANT_URL: str | None = _env("HOME_ASSISTANT_URL")
    HOME_ASSISTANT_TOKEN: str | None = _env("HOME_ASSISTANT_TOKEN")

    SEARCH_API_KEY: str | None = _env("SEARCH_API_KEY")
    SEARCH_ENGINE_ID: str | None = _env("SEARCH_ENGINE_ID")

    # ── Agent Config ─────────────────────────────────────
    AGENTS_CONFIG_PATH: str = _env("AGENTS_CONFIG_PATH", "/app/agents.json")

    # ── Redis ────────────────────────────────────────────
    REDIS_URL: str = _env("REDIS_URL", "redis://redis:6379/0")

    # ── Security ─────────────────────────────────────────
    ADMIN_USER_IDS: list[str] = json.loads(_env("ADMIN_USER_IDS", "[]"))
    ADMIN_PIN: str = _env("ADMIN_PIN", "0000")

    def get_notion_databases(self) -> dict[str, str | None]:
        return {
            "calendar": self.NOTION_CALENDAR_DB,
            "tasks": self.NOTION_TASKS_DB,
            "projects": self.NOTION_PROJECTS_DB,
            "notes": self.NOTION_NOTES_DB,
        }


settings = Settings()
