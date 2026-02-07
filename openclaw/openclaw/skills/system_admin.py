"""System administration skill — server monitoring and management."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from typing import ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill

logger = logging.getLogger(__name__)

# Commands allowed for T1+ users (read-only)
_SAFE_COMMANDS = {
    "disk": ["df", "-h"],
    "memory": ["free", "-h"],
    "cpu": ["top", "-bn1", "-l1"],  # single iteration
    "uptime": ["uptime"],
    "docker_ps": ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
    "docker_stats": ["docker", "stats", "--no-stream", "--format", "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"],
    "ports": ["ss", "-tlnp"],
    "services": ["systemctl", "list-units", "--type=service", "--state=running", "--no-pager"],
}

# Commands requiring T3+ (write operations)
_ADMIN_COMMANDS = {
    "docker_restart": ["docker", "restart"],
    "docker_logs": ["docker", "logs", "--tail", "50"],
    "service_restart": ["systemctl", "restart"],
    "service_stop": ["systemctl", "stop"],
    "service_start": ["systemctl", "start"],
}


class SystemAdminSkill(BaseSkill):
    name: ClassVar[str] = "system_admin"
    description: ClassVar[str] = "Server monitoring: disk, CPU, memory, Docker, services"
    min_tier: ClassVar[int] = 1
    examples: ClassVar[list[str]] = [
        "check disk space",
        "docker status",
        "system health",
        "restart container nginx",
    ]

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        text = ctx.message.content.lower().strip()
        entities = ctx.match.entities

        # Determine which command to run
        cmd = self._resolve_command(text, entities, ctx.user_tier)
        if cmd is None:
            return self._error(
                "I couldn't determine what system command to run. "
                "Try: 'check disk space', 'memory usage', 'docker status', etc."
            )

        if isinstance(cmd, str):
            # cmd is an error message (insufficient tier)
            return self._error(cmd)

        try:
            result = await self._run_command(cmd)
            return self._reply(f"```\n{result}\n```")
        except Exception as e:
            logger.exception("System command failed: %s", cmd)
            return self._error(f"Command failed: {e}")

    def _resolve_command(
        self, text: str, entities: dict, user_tier: int
    ) -> list[str] | str | None:
        """Map user intent to a safe command list."""
        # Check for admin commands first
        action = entities.get("action", "")
        target = entities.get("target", "")

        if any(w in text for w in ("restart", "stop", "start")):
            if user_tier < 3:
                return "This action requires tier 3 access. Ask an admin for help."

            if "docker" in text or "container" in text:
                container = target or self._extract_target(text)
                if container:
                    verb = "restart"
                    if "stop" in text:
                        verb = "stop"
                    elif "start" in text:
                        verb = "start"
                    return ["docker", verb, container]

            if "service" in text:
                service = target or self._extract_target(text)
                if service:
                    verb = "restart"
                    if "stop" in text:
                        verb = "stop"
                    elif "start" in text:
                        verb = "start"
                    return ["systemctl", verb, service]

        if "docker" in text and "log" in text:
            if user_tier < 3:
                return "Docker logs require tier 3 access."
            container = target or self._extract_target(text)
            if container:
                return ["docker", "logs", "--tail", "50", container]
            return _SAFE_COMMANDS["docker_ps"]

        # Safe read-only commands
        if any(w in text for w in ("disk", "storage", "space", "df")):
            return _SAFE_COMMANDS["disk"]
        if any(w in text for w in ("memory", "ram", "mem", "free")):
            return _SAFE_COMMANDS["memory"]
        if any(w in text for w in ("cpu", "load", "top")):
            return _SAFE_COMMANDS["cpu"]
        if "uptime" in text:
            return _SAFE_COMMANDS["uptime"]
        if "docker" in text and any(w in text for w in ("stat", "resource")):
            return _SAFE_COMMANDS["docker_stats"]
        if any(w in text for w in ("docker", "container")):
            return _SAFE_COMMANDS["docker_ps"]
        if any(w in text for w in ("port", "listen")):
            return _SAFE_COMMANDS["ports"]
        if any(w in text for w in ("service", "systemctl", "unit")):
            return _SAFE_COMMANDS["services"]

        # Generic "system status" / "health"
        if any(w in text for w in ("status", "health", "system", "info", "check")):
            return None  # Will trigger multi-check below

        return None

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        text = ctx.message.content.lower().strip()
        entities = ctx.match.entities

        cmd = self._resolve_command(text, entities, ctx.user_tier)

        # If None, do a comprehensive status check
        if cmd is None:
            return await self._comprehensive_status()

        if isinstance(cmd, str):
            return self._error(cmd)

        try:
            result = await self._run_command(cmd)
            return self._reply(f"```\n{result}\n```")
        except Exception as e:
            logger.exception("System command failed: %s", cmd)
            return self._error(f"Command failed: {e}")

    async def _comprehensive_status(self) -> SkillResponse:
        """Run multiple checks and combine results."""
        checks = {
            "Disk": _SAFE_COMMANDS["disk"],
            "Memory": _SAFE_COMMANDS["memory"],
            "Uptime": _SAFE_COMMANDS["uptime"],
        }

        # Add docker if available
        if shutil.which("docker"):
            checks["Docker"] = _SAFE_COMMANDS["docker_ps"]

        parts = []
        for label, cmd in checks.items():
            try:
                result = await self._run_command(cmd)
                parts.append(f"**{label}:**\n```\n{result}\n```")
            except Exception as e:
                parts.append(f"**{label}:** Error — {e}")

        return self._reply("\n".join(parts))

    @staticmethod
    def _extract_target(text: str) -> str | None:
        """Extract a service/container name from text."""
        # Match patterns like "restart nginx", "container openclaw"
        match = re.search(
            r"(?:restart|stop|start|logs?)\s+(?:container\s+|service\s+)?(\w[\w.-]*)",
            text,
        )
        return match.group(1) if match else None

    @staticmethod
    async def _run_command(cmd: list[str], timeout: float = 30.0) -> str:
        """Run a shell command safely with timeout."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return "Command timed out."

        output = stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            return f"{output}\n\nError (exit {proc.returncode}):\n{err}" if output else f"Error: {err}"
        return output or "(no output)"
