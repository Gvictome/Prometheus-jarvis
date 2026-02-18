"""Overseer configuration: security policies, schedules, governance rules."""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Agent2State(str, Enum):
    """Operational states for the Security Protocol Agent."""

    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"


# ── The immutable base security prompt ────────────────────
# This MUST NOT change without human approval via Agent 1.
_BASE_SECURITY_PROMPT = """\
Personal Use Security Protocols (Strongly Recommended)
Because this agent operates with high-privilege capabilities (shell execution, \
file management, browser automation), the following safeguards should be \
considered the minimum baseline for personal experimentation.

1. Identity & Access Control
Adopt a deny-by-default posture.
DM Policy: Set dmPolicy to allowlist or pairing
Pairing Codes: Require a 6-digit pairing code for all new connections

2. Execution Isolation (Sandboxing)
Never run the agent with unrestricted access to your host OS.
Docker Sandboxing: Enable full sandboxing to isolate execution
Workspace Constraints: Limit filesystem access to a dedicated workspace directory

3. Command Governance & Auditing
Keep a human in the loop for risky operations.
Approval Mode: Require explicit confirmation before executing high-risk commands
Command Filtering: Block destructive or privilege-escalation commands

4. Network Layer Security
Do not expose the agent publicly.
Loopback Binding: Bind services to 127.0.0.1
Private Access Only: Use secure tunnels (e.g., Tailscale) if remote access is \
required — never open ports directly"""


class SecurityPolicy(BaseModel):
    """The security policy configuration.

    The ``prompt`` field is immutable unless a human-approved change request
    is processed through Agent 1.
    """

    prompt: str = _BASE_SECURITY_PROMPT
    prompt_version: int = 1
    prompt_last_modified: datetime = Field(default_factory=datetime.utcnow)
    prompt_modified_by: str = "system_init"


class GovernanceConfig(BaseModel):
    """Governance rules mirroring the hardened configuration."""

    approval_required: list[str] = Field(
        default=["shell-command", "file-delete", "git-push", "ssh-hardening"]
    )
    blocked_commands: list[str] = Field(
        default=["rm -rf /", "sudo", "chmod", "shutdown"]
    )


class GatewayConfig(BaseModel):
    """Gateway binding configuration."""

    host: str = "127.0.0.1"
    port: int = 18789
    pairing: bool = True


class SecurityConfig(BaseModel):
    """Security settings mirroring the hardened configuration."""

    dm_policy: str = "allowlist"
    allow_from: list[str] = Field(default_factory=list)
    sandbox: str = "all"
    workspace: str = "./openclaw-workspace"
    workspace_access: str = "rw"


class AuditSchedule(BaseModel):
    """When Agent 2 runs its automated audits."""

    enabled: bool = True
    cron_hour: int = 6
    cron_minute: int = 0
    interval_hours: int | None = None


class OverseerConfig(BaseModel):
    """Top-level overseer configuration."""

    name: str = "Personal-Local-Agent"
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    security_policy: SecurityPolicy = Field(default_factory=SecurityPolicy)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    audit_schedule: AuditSchedule = Field(default_factory=AuditSchedule)
    agent2_state: Agent2State = Agent2State.RUNNING
    check_in_interval_hours: int = 8


def get_base_security_prompt() -> str:
    """Return the canonical immutable security prompt.

    Used for comparison when validating that the prompt has not been
    tampered with.
    """
    return _BASE_SECURITY_PROMPT
