"""Agent 2 — Security Protocol Agent.

Handles automated security audits according to the base security prompt.
Runs checks against the four protocol domains:
  1. Identity & Access Control
  2. Execution Isolation
  3. Command Governance & Auditing
  4. Network Layer Security

This agent NEVER modifies its own security prompt.  It only reads it.
All configuration changes must flow through Agent 1 with human approval.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from openclaw.inference.router import InferenceRouter
from openclaw.memory.store import MemoryStore
from openclaw.overseer.config import (
    Agent2State,
    OverseerConfig,
    get_base_security_prompt,
)
from openclaw.overseer.schemas import AuditFinding, AuditReport, AuditSeverity

logger = logging.getLogger(__name__)


class SecurityProtocolAgent:
    """Agent 2: Autonomous security auditor.

    - Runs security checks matching the 4 protocol domains
    - Stores results in MemoryStore audit_log
    - Reports findings to Agent 1
    - NEVER modifies its own security prompt or config
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
        self._state: Agent2State = config.agent2_state
        self._last_report: AuditReport | None = None
        self._started_at: float = time.time()

    # ── Properties ────────────────────────────────────────

    @property
    def state(self) -> Agent2State:
        return self._state

    @property
    def last_report(self) -> AuditReport | None:
        return self._last_report

    @property
    def uptime_hours(self) -> float:
        return (time.time() - self._started_at) / 3600

    # ── Lifecycle ─────────────────────────────────────────

    def start(self) -> None:
        self._state = Agent2State.RUNNING
        logger.info("SecurityProtocolAgent started")

    def stop(self) -> None:
        self._state = Agent2State.STOPPED
        logger.info("SecurityProtocolAgent stopped")

    def pause(self) -> None:
        self._state = Agent2State.PAUSED
        logger.info("SecurityProtocolAgent paused")

    # ── Main Audit Entrypoint ─────────────────────────────

    async def run_audit(self, trigger: str = "scheduled") -> AuditReport:
        """Execute a full security audit across all 4 protocol domains."""
        if self._state == Agent2State.STOPPED:
            return AuditReport(
                report_id=str(uuid.uuid4())[:8],
                trigger=trigger,
                summary="Agent is stopped. No audit performed.",
            )

        start_time = time.time()
        report_id = str(uuid.uuid4())[:8]
        findings: list[AuditFinding] = []

        check_methods = [
            self._check_identity_access,
            self._check_execution_isolation,
            self._check_command_governance,
            self._check_network_security,
        ]

        for check in check_methods:
            try:
                result = await check()
                findings.extend(result)
            except Exception as exc:
                logger.exception("Audit check %s failed", check.__name__)
                findings.append(
                    AuditFinding(
                        check_name=check.__name__,
                        severity=AuditSeverity.WARNING,
                        summary=f"Check failed with error: {exc}",
                    )
                )

        # Verify prompt integrity
        prompt_finding = self._verify_prompt_integrity()
        if prompt_finding:
            findings.append(prompt_finding)

        duration = time.time() - start_time
        summary = await self._generate_summary(findings)

        report = AuditReport(
            report_id=report_id,
            trigger=trigger,
            findings=findings,
            summary=summary,
            duration_seconds=round(duration, 2),
        )

        self._last_report = report

        # Persist to audit_log
        self._store.log_audit(
            user_id="overseer:agent2",
            action="security_audit",
            detail=json.dumps(
                {
                    "report_id": report_id,
                    "trigger": trigger,
                    "findings_count": len(findings),
                    "critical": report.critical_count,
                    "warnings": report.warning_count,
                    "duration_s": report.duration_seconds,
                }
            ),
            tier=5,
        )

        return report

    # ── Protocol Domain 1: Identity & Access Control ──────

    async def _check_identity_access(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []

        # Check for SSH authorized keys
        output = await self._run(
            ["find", "/root/.ssh", "-name", "authorized_keys", "-exec", "cat", "{}", ";"]
        )
        if output and "command not found" not in output.lower() and "No such file" not in output:
            key_count = len(
                [line for line in output.strip().split("\n") if line.strip() and not line.startswith("#")]
            )
            severity = AuditSeverity.INFO if key_count <= 2 else AuditSeverity.WARNING
            findings.append(
                AuditFinding(
                    check_name="ssh_authorized_keys",
                    severity=severity,
                    summary=f"{key_count} SSH authorized key(s) found",
                    raw_output=output[:500],
                )
            )

        # Check active user sessions
        output = await self._run(["who"])
        if output and output.strip() and "command not found" not in output.lower():
            user_count = len(output.strip().split("\n"))
            severity = AuditSeverity.INFO if user_count <= 1 else AuditSeverity.WARNING
            findings.append(
                AuditFinding(
                    check_name="active_users",
                    severity=severity,
                    summary=f"{user_count} active user session(s)",
                    raw_output=output[:500],
                )
            )
        else:
            findings.append(
                AuditFinding(
                    check_name="active_users",
                    severity=AuditSeverity.INFO,
                    summary="No active user sessions detected",
                )
            )

        # Check for users with UID 0 (besides root)
        output = await self._run(["awk", "-F:", "$3==0 {print $1}", "/etc/passwd"])
        if output and "command not found" not in output.lower():
            root_users = [u.strip() for u in output.split("\n") if u.strip()]
            if len(root_users) > 1:
                findings.append(
                    AuditFinding(
                        check_name="uid_zero_users",
                        severity=AuditSeverity.CRITICAL,
                        summary=f"Multiple UID-0 users found: {', '.join(root_users)}",
                        raw_output=output,
                    )
                )

        return findings

    # ── Protocol Domain 2: Execution Isolation ────────────

    async def _check_execution_isolation(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []

        # Check Docker containers
        output = await self._run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"])
        if output and "command not found" not in output.lower():
            container_count = len([line for line in output.strip().split("\n") if line.strip()])
            findings.append(
                AuditFinding(
                    check_name="docker_containers",
                    severity=AuditSeverity.INFO,
                    summary=f"Docker running, {container_count} container(s) active",
                    raw_output=output[:500],
                )
            )

            # Check for privileged containers
            for line in output.strip().split("\n"):
                container = line.split("\t")[0].strip()
                if not container:
                    continue
                inspect = await self._run(
                    ["docker", "inspect", "--format", "{{.HostConfig.Privileged}}", container]
                )
                if inspect and "true" in inspect.lower():
                    findings.append(
                        AuditFinding(
                            check_name="privileged_container",
                            severity=AuditSeverity.CRITICAL,
                            summary=f"Container '{container}' is running in privileged mode",
                        )
                    )
        else:
            findings.append(
                AuditFinding(
                    check_name="docker_containers",
                    severity=AuditSeverity.WARNING,
                    summary="Docker not available or not running",
                )
            )

        # Check workspace directory constraints
        workspace = self._config.security.workspace
        output = await self._run(["ls", "-la", workspace])
        if "No such file" in (output or ""):
            findings.append(
                AuditFinding(
                    check_name="workspace_exists",
                    severity=AuditSeverity.WARNING,
                    summary=f"Designated workspace {workspace} does not exist",
                )
            )
        elif output:
            findings.append(
                AuditFinding(
                    check_name="workspace_exists",
                    severity=AuditSeverity.INFO,
                    summary=f"Workspace {workspace} exists and is accessible",
                )
            )

        return findings

    # ── Protocol Domain 3: Command Governance & Auditing ──

    async def _check_command_governance(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []

        # Check audit_log for recent high-risk actions
        try:
            rows = self._store.conn.execute(
                "SELECT action, detail, user_id, created_at FROM audit_log "
                "WHERE created_at >= datetime('now', '-24 hours') "
                "AND (action LIKE '%shell%' OR action LIKE '%admin%' "
                "     OR action LIKE '%security%') "
                "ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            if rows:
                findings.append(
                    AuditFinding(
                        check_name="recent_audit_events",
                        severity=AuditSeverity.INFO,
                        summary=f"{len(rows)} security-relevant audit events in last 24h",
                        detail=json.dumps([dict(r) for r in rows[:10]], default=str),
                    )
                )
        except Exception as exc:
            logger.warning("Could not query audit_log: %s", exc)

        # Check for blocked command patterns in recent shell history
        blocked = self._config.governance.blocked_commands
        output = await self._run(
            ["bash", "-c", "history 50 2>/dev/null || cat ~/.bash_history 2>/dev/null | tail -50"]
        )
        if output and "command not found" not in output.lower():
            for cmd in blocked:
                if cmd.lower() in output.lower():
                    findings.append(
                        AuditFinding(
                            check_name="blocked_command_detected",
                            severity=AuditSeverity.CRITICAL,
                            summary=f"Blocked command pattern '{cmd}' found in recent history",
                        )
                    )

        # Verify governance config integrity
        if not self._config.governance.approval_required:
            findings.append(
                AuditFinding(
                    check_name="governance_config",
                    severity=AuditSeverity.CRITICAL,
                    summary="No commands require approval — governance may be misconfigured",
                )
            )

        return findings

    # ── Protocol Domain 4: Network Layer Security ─────────

    async def _check_network_security(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []

        # Check listening ports
        output = await self._run(["ss", "-tlnp"])
        if output and "command not found" not in output.lower():
            lines = output.strip().split("\n")
            for line in lines[1:]:  # Skip header
                if ("0.0.0.0:" in line or ":::" in line) and "127.0.0.1" not in line:
                    findings.append(
                        AuditFinding(
                            check_name="open_port",
                            severity=AuditSeverity.WARNING,
                            summary=f"Service listening on all interfaces: {line.strip()[:100]}",
                            raw_output=line,
                        )
                    )

            findings.append(
                AuditFinding(
                    check_name="listening_ports",
                    severity=AuditSeverity.INFO,
                    summary=f"{len(lines) - 1} listening TCP port(s) detected",
                    raw_output=output[:500],
                )
            )

        # Check for external established connections
        output = await self._run(["ss", "-tunp", "state", "established"])
        if output and "command not found" not in output.lower():
            lines = output.strip().split("\n")
            external = [
                line
                for line in lines
                if line.strip() and "127.0.0.1" not in line and "::1" not in line
            ]
            if len(external) > 5:
                findings.append(
                    AuditFinding(
                        check_name="external_connections",
                        severity=AuditSeverity.WARNING,
                        summary=f"{len(external)} external connections detected",
                        raw_output="\n".join(external[:10]),
                    )
                )

        # Check fail2ban
        output = await self._run(["fail2ban-client", "status"])
        if (
            output
            and "command not found" not in output.lower()
            and "error" not in output.lower()
        ):
            findings.append(
                AuditFinding(
                    check_name="fail2ban",
                    severity=AuditSeverity.INFO,
                    summary="fail2ban is active",
                    raw_output=output[:500],
                )
            )
        else:
            findings.append(
                AuditFinding(
                    check_name="fail2ban",
                    severity=AuditSeverity.WARNING,
                    summary="fail2ban is not installed or not running",
                )
            )

        # Check firewall (ufw first, then iptables)
        output = await self._run(["ufw", "status"])
        if output and "active" in output.lower() and "inactive" not in output.lower():
            findings.append(
                AuditFinding(
                    check_name="firewall",
                    severity=AuditSeverity.INFO,
                    summary="UFW firewall is active",
                    raw_output=output[:500],
                )
            )
        else:
            output = await self._run(["iptables", "-L", "-n", "--line-numbers"])
            if output and "command not found" not in output.lower():
                rule_count = len(
                    [
                        line
                        for line in output.split("\n")
                        if line.strip()
                        and not line.startswith("Chain")
                        and not line.startswith("num")
                    ]
                )
                if rule_count > 0:
                    findings.append(
                        AuditFinding(
                            check_name="firewall",
                            severity=AuditSeverity.INFO,
                            summary=f"iptables has {rule_count} rules configured",
                        )
                    )
                else:
                    findings.append(
                        AuditFinding(
                            check_name="firewall",
                            severity=AuditSeverity.WARNING,
                            summary="No firewall rules configured",
                        )
                    )

        return findings

    # ── Prompt Integrity ──────────────────────────────────

    def _verify_prompt_integrity(self) -> AuditFinding | None:
        """Verify the active security prompt matches the canonical base."""
        canonical = get_base_security_prompt()
        current = self._config.security_policy.prompt

        if current != canonical:
            return AuditFinding(
                check_name="prompt_integrity",
                severity=AuditSeverity.CRITICAL,
                summary="Active security prompt differs from canonical base prompt",
                detail=(
                    f"Version: {self._config.security_policy.prompt_version}, "
                    f"Modified by: {self._config.security_policy.prompt_modified_by}"
                ),
            )
        return None

    # ── LLM Summary ───────────────────────────────────────

    async def _generate_summary(self, findings: list[AuditFinding]) -> str:
        """Use the InferenceRouter to generate a human-readable summary."""
        if not findings:
            return "No issues detected. All security checks passed."

        findings_text = "\n".join(
            f"- [{f.severity.value.upper()}] {f.check_name}: {f.summary}"
            for f in findings
        )

        try:
            result = await self._inference.generate(
                prompt=(
                    f"Summarize these security audit findings in 2-3 sentences. "
                    f"Highlight any critical issues first.\n\n{findings_text}"
                ),
                system="You are a security analyst. Be concise and actionable.",
                force_provider="ollama",
                temperature=0.3,
            )
            return result["text"]
        except Exception:
            # Fallback: generate summary without LLM
            critical = sum(1 for f in findings if f.severity == AuditSeverity.CRITICAL)
            warnings = sum(1 for f in findings if f.severity == AuditSeverity.WARNING)
            return (
                f"Audit complete: {len(findings)} findings "
                f"({critical} critical, {warnings} warnings, "
                f"{len(findings) - critical - warnings} info)."
            )

    # ── Command Runner ────────────────────────────────────

    @staticmethod
    async def _run(cmd: list[str], timeout: float = 15.0) -> str:
        """Run a command safely with timeout.

        Follows the same pattern as SecurityMonitorSkill._run().
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace").strip()
            if proc.returncode != 0 and not output:
                return stderr.decode("utf-8", errors="replace").strip()
            return output or "(no output)"
        except FileNotFoundError:
            return f"Command not found: {cmd[0]}"
        except asyncio.TimeoutError:
            return "Command timed out."
