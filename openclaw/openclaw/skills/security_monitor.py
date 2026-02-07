"""Security monitoring skill — port scanning, fail2ban, disk alerts."""

from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class SecurityMonitorSkill(BaseSkill):
    name: ClassVar[str] = "security_monitor"
    description: ClassVar[str] = "Security monitoring: ports, fail2ban, connections, login attempts"
    min_tier: ClassVar[int] = 2
    examples: ClassVar[list[str]] = [
        "security check",
        "open ports",
        "fail2ban status",
        "suspicious activity",
    ]

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        text = ctx.message.content.lower()

        if "port" in text:
            return await self._check_ports()
        if "fail2ban" in text:
            return await self._check_fail2ban()
        if "connection" in text or "suspicious" in text:
            return await self._check_connections()
        if "login" in text:
            return await self._check_auth_log()

        # Full security report
        return await self._full_report()

    async def _full_report(self) -> SkillResponse:
        parts = []

        for label, coro in [
            ("Open Ports", self._check_ports()),
            ("Active Connections", self._check_connections()),
            ("Fail2Ban", self._check_fail2ban()),
            ("Recent Auth", self._check_auth_log()),
        ]:
            try:
                result = await coro
                parts.append(f"**{label}:**\n{result.text}")
            except Exception as e:
                parts.append(f"**{label}:** Error — {e}")

        return self._reply("\n\n".join(parts))

    async def _check_ports(self) -> SkillResponse:
        output = await self._run(["ss", "-tlnp"])
        return self._reply(f"```\n{output}\n```")

    async def _check_fail2ban(self) -> SkillResponse:
        output = await self._run(["fail2ban-client", "status"])
        if "command not found" in output.lower() or "error" in output.lower():
            return self._reply("fail2ban is not installed or not running.")
        return self._reply(f"```\n{output}\n```")

    async def _check_connections(self) -> SkillResponse:
        output = await self._run(["ss", "-tunp"])
        # Filter for ESTAB connections only
        lines = output.split("\n")
        estab = [l for l in lines if "ESTAB" in l or l.startswith("Netid")]
        if len(estab) <= 1:
            return self._reply("No established external connections.")
        return self._reply(f"```\n" + "\n".join(estab[:20]) + "\n```")

    async def _check_auth_log(self) -> SkillResponse:
        # Last 20 auth events
        output = await self._run(
            ["journalctl", "-u", "ssh", "-n", "20", "--no-pager", "-o", "short"]
        )
        if not output or "No entries" in output:
            # Try auth.log directly
            output = await self._run(["tail", "-20", "/var/log/auth.log"])
        return self._reply(f"```\n{output}\n```")

    @staticmethod
    async def _run(cmd: list[str], timeout: float = 15.0) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            output = stdout.decode("utf-8", errors="replace").strip()
            if proc.returncode != 0 and not output:
                return stderr.decode("utf-8", errors="replace").strip()
            return output or "(no output)"
        except FileNotFoundError:
            return f"Command not found: {cmd[0]}"
        except asyncio.TimeoutError:
            return "Command timed out."
