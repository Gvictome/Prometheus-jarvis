"""Agent 1 — Human-in-the-Loop Overseer.

Controls Agent 2 (SecurityProtocolAgent) and Agent 3 (KeyVaultAgent).
Reports findings to the human.  Manages approval requests for security
prompt / config changes and API key access.
Proactively checks in with the human on a schedule.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from openclaw.inference.router import InferenceRouter
from openclaw.memory.store import MemoryStore
from openclaw.overseer.config import (
    Agent2State,
    OverseerConfig,
    get_base_security_prompt,
)
from openclaw.overseer.schemas import (
    ApprovalRequest,
    ApprovalStatus,
    AuditReport,
    CheckInReport,
)
from openclaw.overseer.keyvault_agent import KeyVaultAgent
from openclaw.overseer.security_protocol_agent import SecurityProtocolAgent

logger = logging.getLogger(__name__)


class OverseerAgent:
    """Agent 1: Human-in-the-loop coordinator.

    Responsibilities:
      - Starts / stops / configures Agent 2 (Security Protocol)
      - Controls Agent 3 (KeyVault) — enforces approval before key disclosure
      - Manages approval workflow for prompt, config, and key access changes
      - Generates check-in reports for the human
      - Relays Agent 2's audit findings in human-readable form
    """

    def __init__(
        self,
        config: OverseerConfig,
        store: MemoryStore,
        inference: InferenceRouter,
    ):
        self._config = config
        self._store = store
        self._inference = inference
        self._agent2 = SecurityProtocolAgent(config, store, inference)
        self._agent3 = KeyVaultAgent(store)
        self._pending_approvals: dict[str, ApprovalRequest] = {}
        self._started_at: float = time.time()

        if config.agent2_state == Agent2State.RUNNING:
            self._agent2.start()

    # ── Public accessors ──────────────────────────────────

    @property
    def agent2(self) -> SecurityProtocolAgent:
        return self._agent2

    @property
    def agent3(self) -> KeyVaultAgent:
        return self._agent3

    @property
    def config(self) -> OverseerConfig:
        return self._config

    # ── Agent 2 Control ───────────────────────────────────

    def start_agent2(self) -> str:
        self._agent2.start()
        self._config.agent2_state = Agent2State.RUNNING
        self._store.log_audit(
            user_id="overseer:agent1",
            action="agent2_start",
            detail="Agent 2 started by Agent 1",
            tier=5,
        )
        return "Security Protocol Agent (Agent 2) has been started."

    def stop_agent2(self) -> str:
        self._agent2.stop()
        self._config.agent2_state = Agent2State.STOPPED
        self._store.log_audit(
            user_id="overseer:agent1",
            action="agent2_stop",
            detail="Agent 2 stopped by Agent 1",
            tier=5,
        )
        return "Security Protocol Agent (Agent 2) has been stopped."

    def pause_agent2(self) -> str:
        self._agent2.pause()
        self._config.agent2_state = Agent2State.PAUSED
        self._store.log_audit(
            user_id="overseer:agent1",
            action="agent2_pause",
            detail="Agent 2 paused by Agent 1",
            tier=5,
        )
        return "Security Protocol Agent (Agent 2) has been paused."

    def get_agent2_status(self) -> dict[str, Any]:
        last = self._agent2.last_report
        return {
            "state": self._agent2.state.value,
            "uptime_hours": round(self._agent2.uptime_hours, 2),
            "last_audit_id": last.report_id if last else None,
            "last_audit_at": last.run_at.isoformat() if last else None,
            "last_critical_count": last.critical_count if last else 0,
            "last_warning_count": last.warning_count if last else 0,
        }

    # ── Audit Delegation ─────────────────────────────────

    async def request_audit(self, trigger: str = "manual") -> AuditReport:
        """Request Agent 2 to run an audit and return the report."""
        report = await self._agent2.run_audit(trigger=trigger)

        self._store.log_audit(
            user_id="overseer:agent1",
            action="audit_requested",
            detail=json.dumps(
                {
                    "report_id": report.report_id,
                    "trigger": trigger,
                    "findings": len(report.findings),
                    "critical": report.critical_count,
                }
            ),
            tier=5,
        )

        return report

    def format_report_for_human(self, report: AuditReport) -> str:
        """Format an AuditReport into a human-readable markdown message."""
        lines = [
            f"**Security Audit Report** (ID: {report.report_id})",
            f"Triggered by: {report.trigger} | Duration: {report.duration_seconds}s",
            (
                f"Findings: {len(report.findings)} total "
                f"({report.critical_count} critical, {report.warning_count} warnings)"
            ),
            "",
        ]

        if report.summary:
            lines.append(f"**Summary:** {report.summary}")
            lines.append("")

        for severity_label, severity_val in [
            ("CRITICAL", "critical"),
            ("WARNING", "warning"),
            ("INFO", "info"),
        ]:
            matching = [f for f in report.findings if f.severity.value == severity_val]
            if matching:
                lines.append(f"**{severity_label}:**")
                for finding in matching:
                    lines.append(f"  - [{finding.check_name}] {finding.summary}")
                lines.append("")

        return "\n".join(lines)

    # ── Check-In Reports ──────────────────────────────────

    def generate_check_in(self) -> CheckInReport:
        last = self._agent2.last_report
        return CheckInReport(
            agent2_state=self._agent2.state.value,
            last_audit_summary=last.summary if last else None,
            pending_approvals=len(
                [a for a in self._pending_approvals.values() if a.status == ApprovalStatus.PENDING]
            ),
            critical_findings=last.critical_count if last else 0,
            uptime_hours=round((time.time() - self._started_at) / 3600, 2),
        )

    def format_check_in(self, report: CheckInReport) -> str:
        lines = [
            "**Overseer Check-In**",
            f"Agent 2 status: {report.agent2_state}",
            f"Uptime: {report.uptime_hours:.1f} hours",
        ]
        if report.last_audit_summary:
            lines.append(f"Last audit: {report.last_audit_summary}")
        if report.critical_findings > 0:
            lines.append(f"**{report.critical_findings} critical finding(s) require attention.**")
        if report.pending_approvals > 0:
            lines.append(f"**{report.pending_approvals} pending approval(s) awaiting your decision.**")
        if report.pending_approvals == 0 and report.critical_findings == 0:
            lines.append("All clear. No issues require your attention.")
        return "\n".join(lines)

    # ── Approval Workflow ─────────────────────────────────

    def create_approval_request(
        self,
        request_type: str,
        description: str,
        proposed_change: dict[str, Any],
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            request_id=str(uuid.uuid4())[:8],
            request_type=request_type,
            description=description,
            proposed_change=proposed_change,
        )
        self._pending_approvals[req.request_id] = req

        self._store.log_audit(
            user_id="overseer:agent1",
            action="approval_created",
            detail=json.dumps(
                {
                    "request_id": req.request_id,
                    "type": request_type,
                    "description": description,
                }
            ),
            tier=5,
        )
        return req

    def approve_request(self, request_id: str, approver_id: str) -> str:
        req = self._pending_approvals.get(request_id)
        if not req:
            return f"No pending approval with ID '{request_id}'."
        if req.status != ApprovalStatus.PENDING:
            return f"Request {request_id} is already {req.status.value}."

        req.status = ApprovalStatus.APPROVED
        req.resolved_at = datetime.utcnow()
        req.resolved_by = approver_id

        result = self._apply_approved_change(req)

        self._store.log_audit(
            user_id=approver_id,
            action="approval_approved",
            detail=json.dumps(
                {"request_id": request_id, "type": req.request_type, "result": result}
            ),
            tier=5,
        )
        return f"Approved: {result}"

    def reject_request(self, request_id: str, rejector_id: str) -> str:
        req = self._pending_approvals.get(request_id)
        if not req:
            return f"No pending approval with ID '{request_id}'."
        if req.status != ApprovalStatus.PENDING:
            return f"Request {request_id} is already {req.status.value}."

        req.status = ApprovalStatus.REJECTED
        req.resolved_at = datetime.utcnow()
        req.resolved_by = rejector_id

        self._store.log_audit(
            user_id=rejector_id,
            action="approval_rejected",
            detail=json.dumps({"request_id": request_id, "type": req.request_type}),
            tier=5,
        )
        return f"Request {request_id} has been rejected. No changes applied."

    def list_pending_approvals(self) -> list[ApprovalRequest]:
        return [a for a in self._pending_approvals.values() if a.status == ApprovalStatus.PENDING]

    def _apply_approved_change(self, req: ApprovalRequest) -> str:
        """Apply an approved change to the config."""
        if req.request_type == "prompt_change":
            new_prompt = req.proposed_change.get("new_prompt")
            if new_prompt:
                self._config.security_policy.prompt = new_prompt
                self._config.security_policy.prompt_version += 1
                self._config.security_policy.prompt_last_modified = datetime.utcnow()
                self._config.security_policy.prompt_modified_by = req.resolved_by or "unknown"
                return f"Security prompt updated to version {self._config.security_policy.prompt_version}."
            return "No new_prompt in proposed change."

        if req.request_type == "config_change":
            changes = req.proposed_change
            applied = []
            if "blocked_commands" in changes:
                self._config.governance.blocked_commands = changes["blocked_commands"]
                applied.append("blocked_commands")
            if "approval_required" in changes:
                self._config.governance.approval_required = changes["approval_required"]
                applied.append("approval_required")
            if "allow_from" in changes:
                self._config.security.allow_from = changes["allow_from"]
                applied.append("allow_from")
            if "dm_policy" in changes:
                self._config.security.dm_policy = changes["dm_policy"]
                applied.append("dm_policy")
            if applied:
                return f"Config updated: {', '.join(applied)}"
            return "No recognized config fields in proposed change."

        if req.request_type == "key_access":
            key_id = req.proposed_change.get("key_id")
            if key_id:
                plaintext = self._agent3.reveal_key(key_id, req.resolved_by or "unknown")
                if plaintext:
                    return f"Key revealed: `{plaintext}`"
                return "Key not found in vault."
            return "No key_id in proposed change."

        if req.request_type == "key_add":
            service = req.proposed_change.get("service", "")
            env_var = req.proposed_change.get("env_var", "")
            value = req.proposed_change.get("value", "")
            if service and value:
                entry = self._agent3.add_key(service, env_var, value, req.resolved_by or "unknown")
                return f"Key added for {entry.service} [{entry.key_id}]."
            return "Missing service or value in proposed change."

        if req.request_type == "key_remove":
            key_id = req.proposed_change.get("key_id")
            if key_id:
                removed = self._agent3.remove_key(key_id, req.resolved_by or "unknown")
                return f"Key removed." if removed else f"Key {key_id} not found."
            return "No key_id in proposed change."

        return f"Unknown request type: {req.request_type}"

    # ── Command Handler (called by OverseerSkill) ─────────

    async def handle_command(self, text: str, sender_id: str) -> str:
        """Parse and handle an overseer command from the user."""
        text_lower = text.lower().strip()

        # ── Agent 2 control ───────────────────────────────
        if "start agent" in text_lower or "start security" in text_lower:
            return self.start_agent2()

        if "stop agent" in text_lower or "stop security" in text_lower:
            return self.stop_agent2()

        if "pause agent" in text_lower or "pause security" in text_lower:
            return self.pause_agent2()

        # ── Status ────────────────────────────────────────
        if "status" in text_lower:
            check_in = self.generate_check_in()
            return self.format_check_in(check_in)

        # ── Run audit ─────────────────────────────────────
        if "audit" in text_lower or "scan" in text_lower or "security check" in text_lower:
            report = await self.request_audit(trigger="manual")
            return self.format_report_for_human(report)

        # ── Last report ───────────────────────────────────
        if "last report" in text_lower or "latest report" in text_lower or "findings" in text_lower:
            last = self._agent2.last_report
            if last:
                return self.format_report_for_human(last)
            return "No audit reports yet. Run one with: 'overseer audit'"

        # ── Approval management ───────────────────────────
        if "pending" in text_lower or "approval" in text_lower:
            pending = self.list_pending_approvals()
            if not pending:
                return "No pending approval requests."
            lines = ["**Pending Approvals:**"]
            for a in pending:
                lines.append(f"  - [{a.request_id}] {a.request_type}: {a.description}")
            lines.append("\nUse 'overseer approve <id>' or 'overseer reject <id>' to act.")
            return "\n".join(lines)

        if "approve " in text_lower:
            parts = text_lower.split("approve", 1)
            req_id = parts[1].strip().split()[0] if parts[1].strip() else ""
            if req_id:
                return self.approve_request(req_id, sender_id)
            return "Specify the approval ID. Use 'overseer pending' to see pending requests."

        if "reject " in text_lower:
            parts = text_lower.split("reject", 1)
            req_id = parts[1].strip().split()[0] if parts[1].strip() else ""
            if req_id:
                return self.reject_request(req_id, sender_id)
            return "Specify the request ID to reject."

        # ── Prompt change request (creates approval) ──────
        if "change prompt" in text_lower or "modify prompt" in text_lower or "update prompt" in text_lower:
            if ":" in text:
                new_prompt = text.split(":", 1)[1].strip()
                if new_prompt:
                    req = self.create_approval_request(
                        request_type="prompt_change",
                        description=f"Change security prompt to: {new_prompt[:80]}...",
                        proposed_change={"new_prompt": new_prompt},
                    )
                    return (
                        f"Prompt change request created (ID: {req.request_id}).\n"
                        f"This requires your explicit approval.\n"
                        f"Use 'overseer approve {req.request_id}' to apply, "
                        f"or 'overseer reject {req.request_id}' to discard."
                    )
            return "To request a prompt change, use:\n  overseer change prompt: <your new prompt text>"

        # ── KeyVault commands ──────────────────────────────
        if "keyvault" in text_lower or "key vault" in text_lower or "api key" in text_lower:
            return self._handle_keyvault_command(text, sender_id)

        # ── Show current policy ───────────────────────────
        if "policy" in text_lower or "prompt" in text_lower or "config" in text_lower:
            policy = self._config.security_policy
            return (
                f"**Current Security Policy** (v{policy.prompt_version})\n"
                f"Last modified: {policy.prompt_last_modified.isoformat()}\n"
                f"Modified by: {policy.prompt_modified_by}\n\n"
                f"```\n{policy.prompt}\n```"
            )

        # ── Help ──────────────────────────────────────────
        return (
            "**OpenClaw Overseer Commands:**\n"
            "  - `overseer status` -- Check Agent 2 status and overview\n"
            "  - `overseer audit` -- Run a security audit now\n"
            "  - `overseer last report` -- View the latest audit report\n"
            "  - `overseer start/stop/pause agent` -- Control Agent 2\n"
            "  - `overseer pending` -- View pending approval requests\n"
            "  - `overseer approve <id>` -- Approve a pending request\n"
            "  - `overseer reject <id>` -- Reject a pending request\n"
            "  - `overseer policy` -- View current security policy\n"
            "  - `overseer change prompt: <text>` -- Request prompt change (requires approval)\n"
            "\n"
            "**KeyVault Commands:**\n"
            "  - `overseer keyvault list` -- List all registered API keys (masked)\n"
            "  - `overseer keyvault <service>` -- Request access to a key (requires approval)\n"
            "  - `overseer api key notion` -- Request a specific key (requires approval)\n"
        )

    # ── KeyVault command delegation ───────────────────────

    def _handle_keyvault_command(self, text: str, sender_id: str) -> str:
        """Route keyvault commands through Agent 3 with approval enforcement."""
        result = self._agent3.handle_command(text, sender_id)
        action = result.get("action", "help")

        # List is safe — values are masked
        if action == "list":
            return result["response"]

        # Key reveal requires human approval
        if action == "reveal_requested":
            key_id = result["key_id"]
            service = result["service"]
            masked = result["masked_value"]

            self._store.log_audit(
                user_id=sender_id,
                action="keyvault_reveal_requested",
                detail=json.dumps({"key_id": key_id, "service": service}),
                tier=5,
            )

            req = self.create_approval_request(
                request_type="key_access",
                description=f"Reveal API key for {service} (masked: {masked})",
                proposed_change={"key_id": key_id, "service": service},
            )
            return (
                f"**Key access request created** (ID: {req.request_id})\n"
                f"Service: {service} | Masked: `{masked}`\n\n"
                f"This requires your explicit approval.\n"
                f"Use `overseer approve {req.request_id}` to reveal the key, "
                f"or `overseer reject {req.request_id}` to deny."
            )

        # Add key requires approval
        if action == "add_requested":
            return (
                "To add a key, provide:\n"
                "  `overseer keyvault add <service> <ENV_VAR> <value>`\n"
                "This will create an approval request before the key is stored."
            )

        # Remove key requires approval
        if action == "remove_requested":
            return (
                "To remove a key, provide:\n"
                "  `overseer keyvault remove <key_id>`\n"
                "This will create an approval request before the key is deleted."
            )

        # Help
        return (
            "**KeyVault Commands:**\n"
            "  - `overseer keyvault list` -- List all registered API keys (masked)\n"
            "  - `overseer keyvault <service>` -- Request access to a specific key\n"
            "    Services: notion, anthropic, telegram, home_assistant, search_api\n"
            "  - `overseer keyvault get <key_id>` -- Request access by key ID\n\n"
            "All key reveals require your explicit approval."
        )
