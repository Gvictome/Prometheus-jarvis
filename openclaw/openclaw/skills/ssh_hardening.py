"""SSH & firewall hardening skill — guided hardening with overseer approval."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill

logger = logging.getLogger(__name__)

# ── Command classification ────────────────────────────────
# Safe commands: read-only diagnostics, run immediately
_SAFE_COMMANDS: list[list[str]] = [
    ["sshd", "-T"],
    ["ss", "-tlnp"],
    ["ufw", "status", "verbose"],
    ["fail2ban-client", "status"],
    ["fail2ban-client", "status", "sshd"],
    ["journalctl", "-u", "ssh", "-n", "50", "--no-pager", "-o", "short"],
    ["cat", "/etc/ssh/sshd_config"],
]

# Hardening recommendations: description, command, category
_HARDENING_STEPS: list[dict[str, Any]] = [
    {
        "id": "disable_root",
        "description": "Disable root login",
        "command": ["sed", "-i", "s/^#\\?PermitRootLogin.*/PermitRootLogin no/", "/etc/ssh/sshd_config"],
        "category": "ssh",
        "verify": ["sshd", "-T"],
    },
    {
        "id": "disable_password_auth",
        "description": "Disable password authentication (key-only)",
        "command": ["sed", "-i", "s/^#\\?PasswordAuthentication.*/PasswordAuthentication no/", "/etc/ssh/sshd_config"],
        "category": "ssh",
        "requires_check": "authorized_keys",
    },
    {
        "id": "strong_ciphers",
        "description": "Set strong ciphers (chacha20-poly1305, aes256-gcm, aes128-gcm)",
        "command": [
            "sed", "-i",
            "/^Ciphers/d; /^#Ciphers/a Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com",
            "/etc/ssh/sshd_config",
        ],
        "category": "ssh",
    },
    {
        "id": "idle_timeout",
        "description": "Set idle timeout (300s interval, max 2 missed)",
        "command": [
            "sed", "-i",
            "s/^#\\?ClientAliveInterval.*/ClientAliveInterval 300/; s/^#\\?ClientAliveCountMax.*/ClientAliveCountMax 2/",
            "/etc/ssh/sshd_config",
        ],
        "category": "ssh",
    },
    {
        "id": "max_auth_tries",
        "description": "Limit auth attempts to 3",
        "command": ["sed", "-i", "s/^#\\?MaxAuthTries.*/MaxAuthTries 3/", "/etc/ssh/sshd_config"],
        "category": "ssh",
    },
    {
        "id": "restart_sshd",
        "description": "Restart SSH daemon to apply changes",
        "command": ["systemctl", "restart", "sshd"],
        "category": "ssh",
    },
    {
        "id": "ufw_default_deny",
        "description": "Set UFW default deny incoming",
        "command": ["ufw", "default", "deny", "incoming"],
        "category": "firewall",
    },
    {
        "id": "ufw_allow_ssh",
        "description": "Allow SSH through firewall",
        "command": ["ufw", "allow", "ssh"],
        "category": "firewall",
    },
    {
        "id": "ufw_limit_ssh",
        "description": "Rate-limit SSH connections (6/30s per IP)",
        "command": ["ufw", "limit", "ssh"],
        "category": "firewall",
    },
    {
        "id": "ufw_enable",
        "description": "Enable UFW firewall",
        "command": ["ufw", "--force", "enable"],
        "category": "firewall",
        "requires_check": "ufw_allow_ssh",
    },
]


class SSHHardeningSkill(BaseSkill):
    name: ClassVar[str] = "ssh_hardening"
    description: ClassVar[str] = (
        "SSH & firewall hardening: audit config, harden SSH/firewall, "
        "manage tunnel security with overseer approval"
    )
    min_tier: ClassVar[int] = 2
    examples: ClassVar[list[str]] = [
        "ssh security audit",
        "harden ssh",
        "firewall hardening",
        "ssh tunnel check",
        "ssh hardening apply <id>",
    ]

    def __init__(self, store, inference):
        super().__init__(store, inference)
        self._overseer = None

    def set_overseer(self, overseer) -> None:
        """Inject the OverseerAgent after registration."""
        self._overseer = overseer

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        text = ctx.message.content.lower().strip()
        sender = ctx.message.sender_id

        # Route by keyword
        if re.search(r"\bapply\s+(\S+)", text):
            match = re.search(r"\bapply\s+(\S+)", text)
            return await self._apply_approved(match.group(1), sender)

        if any(kw in text for kw in ("audit", "check", "status")):
            return await self._audit()

        if "firewall" in text or "ufw" in text:
            return await self._propose_firewall(sender)

        if "fail2ban" in text:
            return await self._check_fail2ban()

        if any(kw in text for kw in ("tunnel",)):
            return await self._check_tunnels()

        if any(kw in text for kw in ("harden", "secure", "ssh config", "sshd config")):
            return await self._propose_ssh_hardening(sender)

        if "verify" in text:
            return await self._verify_all()

        # Default: full audit
        return await self._audit()

    # ── Read-only diagnostics ─────────────────────────────

    async def _audit(self) -> SkillResponse:
        """Run read-only diagnostics and show current state + recommendations."""
        parts = ["## SSH & Firewall Security Audit\n"]

        # Current sshd config highlights
        sshd_output = await self._run(["sshd", "-T"])
        if "command not found" not in sshd_output.lower():
            issues = self._analyze_sshd(sshd_output)
            parts.append("### SSH Configuration")
            if issues:
                parts.append("**Issues found:**")
                for issue in issues:
                    parts.append(f"- {issue}")
            else:
                parts.append("SSH configuration looks good.")
            parts.append("")

        # Listening ports
        ports = await self._run(["ss", "-tlnp"])
        parts.append("### Listening Ports")
        parts.append(f"```\n{ports}\n```\n")

        # UFW status
        ufw = await self._run(["ufw", "status", "verbose"])
        parts.append("### Firewall (UFW)")
        if "inactive" in ufw.lower() or "command not found" in ufw.lower():
            parts.append("**UFW is not active.** Run `harden firewall` to set up.")
        else:
            parts.append(f"```\n{ufw}\n```")
        parts.append("")

        # Fail2ban
        f2b = await self._run(["fail2ban-client", "status"])
        parts.append("### Fail2ban")
        if "command not found" in f2b.lower() or "error" in f2b.lower():
            parts.append("Fail2ban is not installed or not running.")
        else:
            parts.append(f"```\n{f2b}\n```")

        parts.append("\n---\nUse `harden ssh` or `harden firewall` to create hardening proposals.")
        return self._reply("\n".join(parts))

    async def _check_fail2ban(self) -> SkillResponse:
        output = await self._run(["fail2ban-client", "status"])
        if "command not found" in output.lower() or "error" in output.lower():
            return self._reply("Fail2ban is not installed or not running.")
        sshd_status = await self._run(["fail2ban-client", "status", "sshd"])
        return self._reply(f"**Fail2ban Status:**\n```\n{output}\n```\n\n"
                           f"**SSH Jail:**\n```\n{sshd_status}\n```")

    async def _check_tunnels(self) -> SkillResponse:
        """Check SSH tunnel-related configuration."""
        parts = ["## SSH Tunnel Security\n"]

        sshd = await self._run(["sshd", "-T"])
        if "command not found" not in sshd.lower():
            for key in ("gatewayports", "allowtcpforwarding", "allowagentforwarding"):
                for line in sshd.split("\n"):
                    if line.strip().startswith(key):
                        parts.append(f"- `{line.strip()}`")

        # Active tunnels
        tunnels = await self._run(["ss", "-tlnp"])
        ssh_tunnels = [l for l in tunnels.split("\n") if "ssh" in l.lower()]
        if ssh_tunnels:
            parts.append("\n### Active SSH Tunnels")
            parts.append(f"```\n" + "\n".join(ssh_tunnels) + "\n```")
        else:
            parts.append("\nNo active SSH tunnels detected.")

        return self._reply("\n".join(parts))

    async def _verify_all(self) -> SkillResponse:
        """Run verification commands after hardening."""
        parts = ["## Post-Hardening Verification\n"]

        sshd = await self._run(["sshd", "-T"])
        if "command not found" not in sshd.lower():
            parts.append("### SSH Config")
            for key in ("permitrootlogin", "passwordauthentication",
                        "pubkeyauthentication", "ciphers",
                        "clientaliveinterval", "clientalivecountmax",
                        "maxauthtries"):
                for line in sshd.split("\n"):
                    if line.strip().startswith(key):
                        parts.append(f"- `{line.strip()}`")

        ufw = await self._run(["ufw", "status", "verbose"])
        parts.append("\n### Firewall")
        parts.append(f"```\n{ufw}\n```")

        f2b = await self._run(["fail2ban-client", "status", "sshd"])
        parts.append("\n### Fail2ban (SSH)")
        parts.append(f"```\n{f2b}\n```")

        return self._reply("\n".join(parts))

    # ── Hardening proposals (require approval) ────────────

    async def _propose_ssh_hardening(self, sender: str) -> SkillResponse:
        """Propose SSH config hardening changes via approval requests."""
        if not self._overseer:
            return self._error("Overseer not configured. Cannot create approval requests.")

        # Safety check: verify authorized_keys exist before proposing password disable
        keys_check = await self._run(["test", "-s", "/root/.ssh/authorized_keys"])
        user_keys = await self._run(["sh", "-c", "ls /home/*/.ssh/authorized_keys 2>/dev/null"])
        has_keys = "no such file" not in keys_check.lower() and (
            "command not found" not in keys_check.lower()
        ) or bool(user_keys.strip())

        ssh_steps = [s for s in _HARDENING_STEPS if s["category"] == "ssh"]
        proposals = []

        for step in ssh_steps:
            # Skip password disable if no authorized_keys found
            if step.get("requires_check") == "authorized_keys" and not has_keys:
                proposals.append(
                    f"- **SKIPPED** `{step['id']}`: {step['description']} "
                    f"— no authorized_keys found. Add SSH keys first."
                )
                continue

            req = self._overseer.create_approval_request(
                request_type="ssh_hardening",
                description=f"[SSH Hardening] {step['description']}",
                proposed_change={
                    "step_id": step["id"],
                    "command": step["command"],
                    "category": step["category"],
                },
            )
            proposals.append(f"- `{req.request_id}` — {step['description']}")

        lines = [
            "## SSH Hardening Proposals\n",
            "The following changes require your approval:\n",
            *proposals,
            "",
            "Review with: `overseer pending`",
            "Approve with: `overseer approve <id>`",
            "Apply with: `ssh hardening apply <id>`",
        ]
        return self._reply("\n".join(lines))

    async def _propose_firewall(self, sender: str) -> SkillResponse:
        """Propose firewall hardening changes via approval requests."""
        if not self._overseer:
            return self._error("Overseer not configured. Cannot create approval requests.")

        fw_steps = [s for s in _HARDENING_STEPS if s["category"] == "firewall"]
        proposals = []

        for step in fw_steps:
            req = self._overseer.create_approval_request(
                request_type="ssh_hardening",
                description=f"[Firewall Hardening] {step['description']}",
                proposed_change={
                    "step_id": step["id"],
                    "command": step["command"],
                    "category": step["category"],
                },
            )
            proposals.append(f"- `{req.request_id}` — {step['description']}")

        lines = [
            "## Firewall Hardening Proposals\n",
            "The following changes require your approval:\n",
            *proposals,
            "",
            "**Important:** SSH is allowed before enabling UFW to prevent lockout.",
            "",
            "Review with: `overseer pending`",
            "Approve with: `overseer approve <id>`",
            "Apply with: `ssh hardening apply <id>`",
        ]
        return self._reply("\n".join(lines))

    # ── Execute approved commands ─────────────────────────

    async def _apply_approved(self, request_id: str, sender: str) -> SkillResponse:
        """Execute a previously approved hardening command."""
        if not self._overseer:
            return self._error("Overseer not configured.")

        # Look up the approval
        req = self._overseer._pending_approvals.get(request_id)
        if not req:
            return self._error(f"No approval request found with ID `{request_id}`.")

        if req.status.value != "approved":
            return self._error(
                f"Request `{request_id}` is **{req.status.value}**, not approved. "
                f"Approve first with: `overseer approve {request_id}`"
            )

        change = req.proposed_change
        cmd = change.get("command")
        step_id = change.get("step_id", "unknown")

        if not cmd:
            return self._error(f"No command found in approval `{request_id}`.")

        # Safety: if enabling UFW, verify SSH is allowed
        if step_id == "ufw_enable":
            ufw_status = await self._run(["ufw", "status"])
            if "22" not in ufw_status and "ssh" not in ufw_status.lower():
                return self._error(
                    "Cannot enable UFW: SSH (port 22) is not allowed. "
                    "Apply `ufw_allow_ssh` first to prevent lockout."
                )

        # Backup sshd_config before SSH changes
        if change.get("category") == "ssh" and step_id != "restart_sshd":
            await self._run(["cp", "/etc/ssh/sshd_config", "/etc/ssh/sshd_config.bak"])

        # Execute the command
        self._overseer._store.log_audit(
            user_id=f"ssh_hardening:{sender}",
            action="hardening_applied",
            detail=f"Applying {step_id}: {' '.join(cmd)}",
            tier=5,
        )

        output = await self._run(cmd)

        # Trigger Agent 2 verification
        audit_report = None
        try:
            audit_report = await self._overseer.request_audit(trigger="ssh_hardening")
        except Exception as exc:
            logger.warning("Post-hardening audit failed: %s", exc)

        parts = [
            f"## Applied: {step_id}\n",
            f"**Command:** `{' '.join(cmd)}`",
            f"**Output:**\n```\n{output}\n```",
        ]

        if audit_report:
            parts.append(f"\n### Agent 2 Verification")
            parts.append(f"Audit triggered. Check results with: `overseer audit`")

        return self._reply("\n".join(parts))

    # ── Helpers ───────────────────────────────────────────

    @staticmethod
    def _analyze_sshd(sshd_output: str) -> list[str]:
        """Analyze sshd -T output for common misconfigurations."""
        issues = []
        config = {}
        for line in sshd_output.split("\n"):
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                config[parts[0].lower()] = parts[1]

        if config.get("permitrootlogin") != "no":
            issues.append("Root login is enabled — should be `no`")
        if config.get("passwordauthentication") != "no":
            issues.append("Password authentication is enabled — consider key-only")
        if config.get("pubkeyauthentication") != "yes":
            issues.append("Public key authentication is not enabled")
        if config.get("maxauthtries", "6") not in ("1", "2", "3"):
            issues.append(f"MaxAuthTries is {config.get('maxauthtries', 'unset')} — recommend 3")
        if config.get("clientaliveinterval", "0") == "0":
            issues.append("No idle timeout configured (ClientAliveInterval is 0)")
        if config.get("x11forwarding") == "yes":
            issues.append("X11 forwarding is enabled — disable if not needed")
        if config.get("allowagentforwarding") == "yes":
            issues.append("Agent forwarding is enabled — disable if not needed")

        return issues

    @staticmethod
    async def _run(cmd: list[str], timeout: float = 15.0) -> str:
        """Execute a command and return its output."""
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
