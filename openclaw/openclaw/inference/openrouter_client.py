"""Async OpenRouter client for cloud inference (OpenAI-compatible API)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from openclaw.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.model = model or settings.OPENROUTER_MODEL
        self.max_tokens = settings.OPENROUTER_MAX_TOKENS

    async def chat(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict | None = None,
    ) -> dict[str, Any]:
        """Multi-turn chat completion via OpenRouter API."""
        chat_messages = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        chat_messages.extend(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/prometheus-jarvis",
            "X-Title": "OpenClaw",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})

        result: dict[str, Any] = {
            "text": choice.get("content") or "",
            "model": self.model,
            "provider": "openrouter",
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "cost_usd": 0.0,  # free tier
        }
        if choice.get("tool_calls"):
            result["tool_calls"] = choice["tool_calls"]
            # Preserve the raw assistant message so callers can replay it verbatim
            result["raw_message"] = choice
        return result

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict | None = None,
    ) -> dict[str, Any]:
        """Single-turn generation (wraps chat)."""
        return await self.chat(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )

    def is_available(self) -> bool:
        return self.api_key is not None
