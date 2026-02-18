"""Agent 3 — KeyVault Agent.

Manages API keys and secrets with mandatory human-in-the-loop approval.

Key principles:
  - Keys are loaded from environment variables at startup
  - Keys are NEVER disclosed without explicit human approval via Agent 1
  - Every key access (approved or denied) is audit-logged
  - Keys are displayed masked (only last 4 chars visible) until approved
  - Adding, removing, or rotating keys requires human approval
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from openclaw.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class KeyEntry(BaseModel):
    """A stored API key entry."""

    key_id: str
    service: str
    env_var: str
    masked_value: str
    added_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime | None = None
    access_count: int = 0


# ── Well-known environment variable mappings ──────────────
# service_name -> env_var_name
_KNOWN_KEYS: dict[str, str] = {
    "notion": "NOTION_TOKEN",
    "anthropic": "ANTHROPIC_API_KEY",
    "telegram": "TELEGRAM_BOT_TOKEN",
    "home_assistant": "HOME_ASSISTANT_TOKEN",
    "search_api": "SEARCH_API_KEY",
    "notion_mcp": "NOTION_API_TOKEN",
}


def _mask_key(value: str) -> str:
    """Mask a key showing only the last 4 characters."""
    if len(value) <= 4:
        return "****"
    return "*" * (len(value) - 4) + value[-4:]


class KeyVaultAgent:
    """Agent 3: Secure API key management.

    - Loads keys from environment on init
    - NEVER returns plaintext keys without approved request
    - All access is audit-logged
    - Controlled by Agent 1 (OverseerAgent)
    """

    def __init__(self, store: MemoryStore):
        self._store = store
        self._keys: dict[str, KeyEntry] = {}
        self._raw_keys: dict[str, str] = {}  # key_id -> plaintext (in-memory only)
        self._load_keys_from_env()

    @property
    def key_count(self) -> int:
        return len(self._keys)

    def _load_keys_from_env(self) -> None:
        """Scan environment for known API keys and register them."""
        for service, env_var in _KNOWN_KEYS.items():
            value = os.environ.get(env_var, "")
            if value and value not in ("", "secret_...", "sk-ant-...", "123456:ABC-DEF..."):
                key_id = str(uuid.uuid4())[:8]
                self._keys[key_id] = KeyEntry(
                    key_id=key_id,
                    service=service,
                    env_var=env_var,
                    masked_value=_mask_key(value),
                )
                self._raw_keys[key_id] = value
                logger.info("KeyVault: loaded key for %s (%s)", service, env_var)

    def list_keys(self) -> list[dict[str, Any]]:
        """List all registered keys (masked)."""
        return [
            {
                "key_id": entry.key_id,
                "service": entry.service,
                "env_var": entry.env_var,
                "masked_value": entry.masked_value,
                "access_count": entry.access_count,
                "last_accessed": entry.last_accessed.isoformat() if entry.last_accessed else None,
            }
            for entry in self._keys.values()
        ]

    def get_key_by_service(self, service: str) -> KeyEntry | None:
        """Find a key entry by service name (case-insensitive)."""
        service_lower = service.lower().strip()
        for entry in self._keys.values():
            if entry.service.lower() == service_lower:
                return entry
        return None

    def get_key_by_id(self, key_id: str) -> KeyEntry | None:
        return self._keys.get(key_id)

    def reveal_key(self, key_id: str, approver_id: str) -> str | None:
        """Return the plaintext key value AFTER approval has been granted.

        This should ONLY be called by OverseerAgent after the human
        has approved the key_access approval request.
        """
        if key_id not in self._raw_keys:
            return None

        entry = self._keys[key_id]
        entry.access_count += 1
        entry.last_accessed = datetime.utcnow()

        self._store.log_audit(
            user_id=approver_id,
            action="keyvault_reveal",
            detail=json.dumps(
                {
                    "key_id": key_id,
                    "service": entry.service,
                    "env_var": entry.env_var,
                }
            ),
            tier=5,
        )

        return self._raw_keys[key_id]

    def add_key(self, service: str, env_var: str, value: str, added_by: str) -> KeyEntry:
        """Register a new key (called after human approval)."""
        key_id = str(uuid.uuid4())[:8]
        entry = KeyEntry(
            key_id=key_id,
            service=service,
            env_var=env_var,
            masked_value=_mask_key(value),
        )
        self._keys[key_id] = entry
        self._raw_keys[key_id] = value

        self._store.log_audit(
            user_id=added_by,
            action="keyvault_add",
            detail=json.dumps({"key_id": key_id, "service": service, "env_var": env_var}),
            tier=5,
        )

        return entry

    def remove_key(self, key_id: str, removed_by: str) -> bool:
        """Remove a key (called after human approval)."""
        entry = self._keys.pop(key_id, None)
        self._raw_keys.pop(key_id, None)
        if entry:
            self._store.log_audit(
                user_id=removed_by,
                action="keyvault_remove",
                detail=json.dumps(
                    {"key_id": key_id, "service": entry.service, "env_var": entry.env_var}
                ),
                tier=5,
            )
            return True
        return False

    def format_key_list(self) -> str:
        """Format the key inventory for human display."""
        if not self._keys:
            return "KeyVault is empty. No API keys registered."

        lines = [f"**KeyVault** ({len(self._keys)} key(s) registered)\n"]
        for entry in self._keys.values():
            accessed = (
                f"accessed {entry.access_count}x, last: {entry.last_accessed.isoformat()}"
                if entry.last_accessed
                else "never accessed"
            )
            lines.append(
                f"  - **{entry.service}** [{entry.key_id}]\n"
                f"    env: `{entry.env_var}` | value: `{entry.masked_value}`\n"
                f"    {accessed}"
            )
        return "\n".join(lines)

    # ── Command handling (called by OverseerAgent) ────────

    def handle_command(self, text: str, sender_id: str) -> dict[str, Any]:
        """Parse a keyvault command. Returns a dict with action + context.

        The OverseerAgent wraps this to enforce the approval workflow.
        This method does NOT reveal keys — it only identifies what the
        user wants so Agent 1 can create the appropriate approval request.
        """
        text_lower = text.lower().strip()

        # List all keys (no approval needed — values are masked)
        if "list" in text_lower or "keys" in text_lower or "inventory" in text_lower:
            return {"action": "list", "response": self.format_key_list()}

        # Request to reveal a specific key (needs approval)
        for service_name in _KNOWN_KEYS:
            if service_name.replace("_", " ") in text_lower or service_name in text_lower:
                entry = self.get_key_by_service(service_name)
                if entry:
                    return {
                        "action": "reveal_requested",
                        "key_id": entry.key_id,
                        "service": entry.service,
                        "masked_value": entry.masked_value,
                    }

        # Generic "get key" / "show key" with key_id
        if "get " in text_lower or "show " in text_lower or "reveal " in text_lower:
            # Try to extract a key_id (8-char hex)
            words = text.split()
            for word in words:
                cleaned = word.strip().lower()
                if len(cleaned) == 8 and self.get_key_by_id(cleaned):
                    entry = self.get_key_by_id(cleaned)
                    return {
                        "action": "reveal_requested",
                        "key_id": entry.key_id,
                        "service": entry.service,
                        "masked_value": entry.masked_value,
                    }

        # Add a new key
        if "add " in text_lower:
            return {"action": "add_requested", "raw_text": text}

        # Remove a key
        if "remove " in text_lower or "delete " in text_lower:
            return {"action": "remove_requested", "raw_text": text}

        # Default: show help
        return {"action": "help"}
