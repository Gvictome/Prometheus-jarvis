"""Overseer data models for audit results, approval requests, and agent state."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditFinding(BaseModel):
    """A single finding from a security audit."""

    check_name: str
    severity: AuditSeverity
    summary: str
    detail: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    raw_output: str | None = None


class AuditReport(BaseModel):
    """Complete report from one audit run."""

    report_id: str
    run_at: datetime = Field(default_factory=datetime.utcnow)
    trigger: str = "scheduled"  # "scheduled", "manual", "agent1_request"
    findings: list[AuditFinding] = Field(default_factory=list)
    summary: str = ""
    duration_seconds: float = 0.0

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == AuditSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == AuditSeverity.WARNING)


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRequest(BaseModel):
    """A request that requires human approval before proceeding."""

    request_id: str
    request_type: str  # "prompt_change", "config_change"
    description: str
    proposed_change: dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = None
    resolved_by: str | None = None


class CheckInReport(BaseModel):
    """Agent 1's periodic check-in message to the human."""

    agent2_state: str
    last_audit_summary: str | None = None
    pending_approvals: int = 0
    critical_findings: int = 0
    uptime_hours: float = 0.0
    next_audit_at: str | None = None
