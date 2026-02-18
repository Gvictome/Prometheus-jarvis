"""Overseer scheduler: runs Agent 2 audits on a cron schedule and
Agent 1 check-ins on an interval.

Uses APScheduler (apscheduler==3.10.4, already in requirements.txt).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from openclaw.memory.store import MemoryStore

if TYPE_CHECKING:
    from openclaw.gateway.router import GatewayRouter
    from openclaw.overseer.overseer_agent import OverseerAgent

logger = logging.getLogger(__name__)


class OverseerScheduler:
    """Manages scheduled audit runs and proactive check-ins."""

    def __init__(
        self,
        overseer: OverseerAgent,
        store: MemoryStore,
        gateway: GatewayRouter | None = None,
    ):
        self._overseer = overseer
        self._store = store
        self._gateway = gateway
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        """Start the scheduler with configured jobs."""
        config = self._overseer.config

        # Schedule Agent 2 audits
        if config.audit_schedule.enabled:
            if config.audit_schedule.interval_hours:
                self._scheduler.add_job(
                    self._run_scheduled_audit,
                    trigger=IntervalTrigger(hours=config.audit_schedule.interval_hours),
                    id="overseer_audit_interval",
                    replace_existing=True,
                    name="Overseer Security Audit (interval)",
                )
            else:
                self._scheduler.add_job(
                    self._run_scheduled_audit,
                    trigger=CronTrigger(
                        hour=config.audit_schedule.cron_hour,
                        minute=config.audit_schedule.cron_minute,
                    ),
                    id="overseer_audit_cron",
                    replace_existing=True,
                    name="Overseer Security Audit (daily)",
                )

        # Schedule Agent 1 check-ins
        if config.check_in_interval_hours > 0:
            self._scheduler.add_job(
                self._run_check_in,
                trigger=IntervalTrigger(hours=config.check_in_interval_hours),
                id="overseer_checkin",
                replace_existing=True,
                name="Overseer Human Check-In",
            )

        self._scheduler.start()
        logger.info("OverseerScheduler started")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("OverseerScheduler stopped")

    def get_next_audit_time(self) -> str | None:
        for job in self._scheduler.get_jobs():
            if "audit" in job.id:
                next_run = job.next_run_time
                return next_run.isoformat() if next_run else None
        return None

    # ── Scheduled Jobs ────────────────────────────────────

    async def _run_scheduled_audit(self) -> None:
        """Execute a scheduled audit via Agent 1 -> Agent 2."""
        logger.info("Running scheduled security audit")
        try:
            report = await self._overseer.request_audit(trigger="scheduled")

            # Notify if critical findings
            if report.critical_count > 0:
                formatted = self._overseer.format_report_for_human(report)
                await self._send_notification(
                    f"**ALERT: Scheduled audit found {report.critical_count} "
                    f"critical issue(s).**\n\n{formatted}"
                )

            self._store.log_audit(
                user_id="overseer:scheduler",
                action="scheduled_audit_complete",
                detail=json.dumps(
                    {
                        "report_id": report.report_id,
                        "findings": len(report.findings),
                        "critical": report.critical_count,
                    }
                ),
                tier=5,
            )
        except Exception:
            logger.exception("Scheduled audit failed")

    async def _run_check_in(self) -> None:
        """Generate and send a proactive check-in to the human."""
        logger.info("Running overseer check-in")
        try:
            check_in = self._overseer.generate_check_in()
            formatted = self._overseer.format_check_in(check_in)

            # Only notify if there is something worth reporting
            if check_in.critical_findings > 0 or check_in.pending_approvals > 0:
                await self._send_notification(formatted)

            self._store.log_audit(
                user_id="overseer:scheduler",
                action="check_in",
                detail=json.dumps(
                    {
                        "critical": check_in.critical_findings,
                        "pending_approvals": check_in.pending_approvals,
                    }
                ),
                tier=5,
            )
        except Exception:
            logger.exception("Check-in failed")

    async def _send_notification(self, text: str) -> None:
        """Store a notification for admin users via the SCHEDULER channel."""
        from openclaw.config import settings

        for admin_id in settings.ADMIN_USER_IDS:
            try:
                conv_id = f"overseer:{admin_id}"
                self._store.get_or_create_conversation(conv_id, "scheduler", "overseer")
                self._store.add_message(conv_id, "assistant", text, "scheduler")
            except Exception:
                logger.exception("Failed to notify admin %s", admin_id)
