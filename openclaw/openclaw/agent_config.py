"""Agent configuration loader for per-sender model routing.

Reads agents.json from the project root (or AGENTS_CONFIG_PATH env var)
and provides helpers to resolve a sender ID to an agent name and to look
up that agent's primary + fallback model list.

Model strings in agents.json use the ``openrouter/<model>`` convention.
The helpers strip the ``openrouter/`` prefix so callers receive the bare
model ID that the OpenRouter API expects.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from openclaw.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

# Default location comes from settings (AGENTS_CONFIG_PATH env var or /app/agents.json).
_DEFAULT_CONFIG_PATH = Path(settings.AGENTS_CONFIG_PATH)


def _load_config(path: Path = _DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load and return the raw agents.json dict.

    Returns an empty dict if the file is missing or invalid so that the
    rest of the system degrades gracefully to env-var based routing.
    """
    if not path.exists():
        logger.warning("agents.json not found at %s — agent routing disabled", path)
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        logger.exception("Failed to parse agents.json at %s", path)
        return {}


# Module-level singleton loaded at import time.
_config: dict[str, Any] = _load_config()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def resolve_agent(sender_id: str) -> str | None:
    """Return the agent name for a given sender ID.

    Iterates the ``routing.bindings`` list and returns the first matching
    agent name.  Returns ``None`` if the sender is not in any binding.

    Args:
        sender_id: The raw sender identifier (e.g. WhatsApp JID or Telegram ID).

    Returns:
        Agent name string such as ``"agent-admin"``, or ``None``.
    """
    bindings: list[dict[str, Any]] = (
        _config.get("routing", {}).get("bindings", [])
    )
    for binding in bindings:
        # Expand any placeholder values (e.g. "DYMANI_ID") via environment variables.
        expanded = [
            os.environ.get(v, v) if v.isupper() and v.replace("_", "").isalpha() else v
            for v in binding.get("from", [])
        ]
        if sender_id in expanded:
            return binding["to"]
    return None


def get_model_config(agent_name: str) -> dict[str, Any] | None:
    """Return the model config dict for a named agent.

    The returned dict has the shape::

        {
            "primary": "anthropic/claude-3-haiku",
            "fallbacks": ["anthropic/claude-opus-4.1", ...]
        }

    The ``openrouter/`` prefix is stripped from all model strings so callers
    receive the bare model ID that the OpenRouter API expects.

    Returns ``None`` if the agent is not found in the config.

    Args:
        agent_name: Agent name such as ``"agent-admin"``.

    Returns:
        Dict with ``primary`` and ``fallbacks`` keys, or ``None``.
    """
    model_configs: dict[str, Any] = (
        _config.get("agents", {})
               .get("defaults", {})
               .get("model", {})
    )
    raw = model_configs.get(agent_name)
    if raw is None:
        return None

    def _strip(model_str: str) -> str:
        """Strip leading ``openrouter/`` prefix from a model string."""
        return model_str.removeprefix("openrouter/")

    return {
        "primary": _strip(raw["primary"]),
        "fallbacks": [_strip(m) for m in raw.get("fallbacks", [])],
    }


def reload_config(path: Path = _DEFAULT_CONFIG_PATH) -> None:
    """Reload agents.json from disk.

    Useful in tests or when the config file is updated at runtime without
    restarting the process.

    Args:
        path: Path to the agents.json file.
    """
    global _config
    _config = _load_config(path)
    logger.info("agents.json reloaded from %s", path)
