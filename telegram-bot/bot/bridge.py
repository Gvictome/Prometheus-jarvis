"""HTTP bridge to OpenClaw gateway."""

from __future__ import annotations

import logging
import os

import httpx

OPENCLAW_URL = os.getenv("OPENCLAW_URL", "http://openclaw:8000")
VOICE_GATEWAY_URL = os.getenv("VOICE_GATEWAY_URL", "http://voice-gateway:8001")

logger = logging.getLogger(__name__)

# Shared async client — created once and reused across requests.
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=60.0)
    return _client


async def close_client() -> None:
    """Shutdown the shared HTTP client gracefully."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def send_message(
    sender_id: str,
    chat_id: int,
    content: str,
    message_type: str = "text",
) -> str:
    """Forward a user message to OpenClaw and return the assistant reply.

    Parameters
    ----------
    sender_id:
        Telegram user ID as a string.
    chat_id:
        Telegram chat ID used to build a stable conversation ID.
    content:
        The text content to send.
    message_type:
        One of "text", "voice", "image", "command".

    Returns
    -------
    str
        The text reply from OpenClaw.
    """
    client = _get_client()
    url = f"{OPENCLAW_URL}/api/v1/message"

    payload = {
        "channel": "telegram",
        "sender_id": str(sender_id),
        "content": content,
        "conversation_id": f"tg-{chat_id}",
        "message_type": message_type,
    }

    logger.info("POST %s  sender=%s  conv=tg-%s", url, sender_id, chat_id)

    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("text", "No response from Jarvis.")
    except httpx.HTTPStatusError as exc:
        logger.error(
            "OpenClaw returned %s: %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        return "Sorry, the AI backend returned an error. Please try again later."
    except httpx.RequestError as exc:
        logger.error("Failed to reach OpenClaw: %s", exc)
        return "Sorry, I cannot reach the AI backend right now. Please try again later."


async def transcribe_voice(voice_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Send an audio file to the voice-gateway for transcription.

    Parameters
    ----------
    voice_bytes:
        Raw bytes of the audio file.
    filename:
        Filename hint sent in the multipart form.

    Returns
    -------
    str
        The transcribed text, or an error message.
    """
    client = _get_client()
    url = f"{VOICE_GATEWAY_URL}/api/transcribe"

    logger.info("POST %s  (%d bytes)", url, len(voice_bytes))

    try:
        files = {"file": (filename, voice_bytes, "audio/ogg")}
        response = await client.post(url, files=files)
        response.raise_for_status()
        data = response.json()
        return data.get("text", "")
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Voice-gateway returned %s: %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        return ""
    except httpx.RequestError as exc:
        logger.error("Failed to reach voice-gateway: %s", exc)
        return ""


async def fetch_skills() -> list[dict]:
    """Retrieve the list of registered skills from OpenClaw.

    Returns
    -------
    list[dict]
        Each dict contains 'name', 'description', 'min_tier', and 'examples'.
    """
    client = _get_client()
    url = f"{OPENCLAW_URL}/api/v1/skills"

    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.error("Failed to fetch skills: %s", exc)
        return []
