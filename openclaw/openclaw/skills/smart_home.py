"""Smart home skill — Home Assistant API integration."""

from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

import httpx

from openclaw.config import settings
from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class SmartHomeSkill(BaseSkill):
    name: ClassVar[str] = "smart_home"
    description: ClassVar[str] = "Control smart home devices via Home Assistant"
    min_tier: ClassVar[int] = 1
    examples: ClassVar[list[str]] = [
        "turn on the living room lights",
        "set thermostat to 72",
        "lock the front door",
    ]

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        if not settings.HOME_ASSISTANT_URL or not settings.HOME_ASSISTANT_TOKEN:
            return self._error(
                "Home Assistant is not configured. Set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN."
            )

        entities = ctx.match.entities
        action = entities.get("action", "").lower()
        device = entities.get("device", "").lower()
        value = entities.get("value", "")

        if not device:
            device = self._extract_device(ctx.message.content)

        if not device:
            return self._error(
                "What device do you want to control? "
                "Try: 'turn on living room lights', 'set thermostat to 72'"
            )

        # Find matching HA entity
        ha_entity = await self._find_entity(device)
        if not ha_entity:
            return self._error(f"I couldn't find a device matching '{device}'.")

        entity_id = ha_entity["entity_id"]
        domain = entity_id.split(".")[0]

        # Determine HA service call
        service = self._resolve_service(domain, action, value)
        if not service:
            return self._error(f"I don't know how to '{action}' a {domain} device.")

        # Execute service call
        result = await self._call_service(
            domain=service["domain"],
            service=service["service"],
            entity_id=entity_id,
            data=service.get("data", {}),
        )

        if result:
            friendly = ha_entity.get("attributes", {}).get("friendly_name", device)
            return self._reply(f"Done — {friendly}: {action} {value}".strip())
        return self._error(f"Failed to {action} {device}.")

    async def _find_entity(self, device_name: str) -> dict[str, Any] | None:
        """Search Home Assistant for a matching entity."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.HOME_ASSISTANT_URL}/api/states",
                    headers={"Authorization": f"Bearer {settings.HOME_ASSISTANT_TOKEN}"},
                )
                resp.raise_for_status()
                states = resp.json()
        except Exception:
            logger.exception("Failed to fetch HA states")
            return None

        device_lower = device_name.lower().replace(" ", "_")
        best_match = None
        best_score = 0

        for entity in states:
            eid = entity.get("entity_id", "").lower()
            friendly = entity.get("attributes", {}).get("friendly_name", "").lower()

            # Exact match on entity_id
            if device_lower in eid:
                return entity

            # Fuzzy match on friendly name
            words = device_lower.split()
            score = sum(1 for w in words if w in friendly)
            if score > best_score:
                best_score = score
                best_match = entity

        return best_match if best_score > 0 else None

    @staticmethod
    def _resolve_service(
        domain: str, action: str, value: str
    ) -> dict[str, Any] | None:
        """Map action + domain to HA service call."""
        if domain == "light":
            if action in ("on", "turn on"):
                svc = {"domain": "light", "service": "turn_on", "data": {}}
                if value and value.isdigit():
                    svc["data"]["brightness_pct"] = int(value)
                return svc
            if action in ("off", "turn off"):
                return {"domain": "light", "service": "turn_off"}
            if action in ("dim", "brighten"):
                pct = int(value) if value and value.isdigit() else (30 if action == "dim" else 100)
                return {"domain": "light", "service": "turn_on", "data": {"brightness_pct": pct}}

        if domain == "switch":
            if action in ("on", "turn on"):
                return {"domain": "switch", "service": "turn_on"}
            if action in ("off", "turn off"):
                return {"domain": "switch", "service": "turn_off"}

        if domain == "climate":
            if value:
                temp = re.search(r"\d+", value)
                if temp:
                    return {
                        "domain": "climate",
                        "service": "set_temperature",
                        "data": {"temperature": int(temp.group())},
                    }

        if domain == "lock":
            if action in ("lock",):
                return {"domain": "lock", "service": "lock"}
            if action in ("unlock",):
                return {"domain": "lock", "service": "unlock"}

        if domain in ("cover", "fan"):
            if action in ("on", "turn on", "open"):
                return {"domain": domain, "service": "turn_on" if domain == "fan" else "open_cover"}
            if action in ("off", "turn off", "close"):
                return {"domain": domain, "service": "turn_off" if domain == "fan" else "close_cover"}

        # Generic toggle fallback
        if action in ("on", "turn on"):
            return {"domain": "homeassistant", "service": "turn_on"}
        if action in ("off", "turn off"):
            return {"domain": "homeassistant", "service": "turn_off"}

        return None

    async def _call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Execute a Home Assistant service call."""
        payload = {"entity_id": entity_id}
        if data:
            payload.update(data)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.HOME_ASSISTANT_URL}/api/services/{domain}/{service}",
                    headers={"Authorization": f"Bearer {settings.HOME_ASSISTANT_TOKEN}"},
                    json=payload,
                )
                return resp.status_code in (200, 201)
        except Exception:
            logger.exception("HA service call failed: %s/%s", domain, service)
            return False

    @staticmethod
    def _extract_device(text: str) -> str:
        """Extract device name from natural language."""
        text = text.lower()
        for prefix in ("turn on", "turn off", "dim", "brighten", "set", "lock", "unlock"):
            if prefix in text:
                after = text.split(prefix, 1)[-1].strip()
                after = re.sub(r"^the\s+", "", after)
                after = re.sub(r"\s+to\s+.*$", "", after)
                return after
        return ""
