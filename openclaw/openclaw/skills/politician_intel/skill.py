"""Politician Intelligence Skill — v0.1

Handles querying and surfacing congressional intelligence connected to
sports betting markets. Integrates with PoliticianDB and the analysis
sub-package to provide alerts, trade lookups, politician profiles, and
gambling legislation tracking via Telegram/WhatsApp.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill
from openclaw.skills.politician_intel.db import PoliticianDB
from openclaw.skills.politician_intel.formatters import (
    format_alert_list,
    format_politician_profile,
    format_trade_list,
    format_bill_list,
    format_briefing,
)

logger = logging.getLogger(__name__)

_DB_PATH = "/data/politician_intel.db"


class PoliticianIntelSkill(BaseSkill):
    """Congressional intelligence tracker — trades, votes, bills, and alerts.

    Intent keywords handled:
        politician alerts         — undelivered/recent alerts ranked by severity
        politician trades         — recent gaming stock trades by tracked members
        politician profile <name> — profile for a specific member
        gambling legislation      — relevant bills above threshold relevance score
        politician briefing       — daily summary of all intelligence categories
    """

    name: ClassVar[str] = "politician_intel"
    description: ClassVar[str] = (
        "Congressional intelligence tracker — gaming stock trades, votes, bills, and alerts"
    )
    min_tier: ClassVar[int] = 1
    examples: ClassVar[list[str]] = [
        "politician alerts",
        "politician trades",
        "politician profile pelosi",
        "gambling legislation",
        "politician briefing",
        "show me gaming stock trades",
        "state gambling bills",
        "congressional intel",
    ]

    def __init__(self, store, inference):
        super().__init__(store, inference)
        self._db: PoliticianDB | None = None

    # ── Public property (mirrors SportsSignalsSkill.db pattern) ──

    @property
    def db(self) -> PoliticianDB:
        """Lazy-initialised database instance."""
        return self._get_db()

    def _get_db(self) -> PoliticianDB:
        """Lazy-initialise PoliticianDB (avoids file creation at import time)."""
        if self._db is None:
            self._db = PoliticianDB(_DB_PATH)
        return self._db

    # ── Main dispatch ─────────────────────────────────────

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        """Route incoming message to the appropriate handler.

        Routing order (most specific first):
            1. Profile lookup  — "politician profile <name>"
            2. Trades          — "politician trades" / "gaming stock trades"
            3. Bills           — "gambling legislation" / "state gambling bills"
            4. Briefing        — "politician briefing"
            5. Alerts          — default / "politician alerts" / "congressional intel"
        """
        text = ctx.message.content.strip()
        text_lower = text.lower()

        try:
            # ── Profile ────────────────────────────────────
            profile_match = re.search(
                r"\bpolitician\s+profile\s+(.+)$", text_lower
            )
            if profile_match:
                return self._handle_profile(profile_match.group(1).strip())

            # ── Trades ─────────────────────────────────────
            if re.search(
                r"\bpolitician\s+trades?\b|\bgaming\s+stock\s+trades?\b"
                r"|\bstock\s+act\s+filings?\b|\bcongressional\s+trades?\b",
                text_lower,
            ):
                return self._handle_trades()

            # ── Legislation ────────────────────────────────
            if re.search(
                r"\bgambling\s+legislation\b|\bgaming\s+bills?\b"
                r"|\bstate\s+gambling\s+bills?\b|\bsports\s+betting\s+bills?\b"
                r"|\bgambling\s+bills?\b",
                text_lower,
            ):
                return self._handle_bills()

            # ── Briefing ───────────────────────────────────
            if re.search(r"\bpolitician\s+briefing\b|\bpolitical\s+briefing\b", text_lower):
                return self._handle_briefing()

            # ── Alerts (default) ───────────────────────────
            return self._handle_alerts()

        except Exception as exc:
            logger.exception("PoliticianIntelSkill.execute failed")
            self.store.log_audit(
                ctx.message.sender_id,
                "politician_intel_error",
                str(exc),
                ctx.user_tier,
            )
            return self._error(f"Politician intel error: {exc}")

    # ── Command handlers ───────────────────────────────────

    def _handle_alerts(self) -> SkillResponse:
        """Return recent undelivered alerts ranked by severity."""
        db = self._get_db()
        alerts = db.get_undelivered_alerts(limit=10)
        if not alerts:
            alerts = db.get_recent_alerts(days=7, limit=10)
        return self._reply(format_alert_list(alerts))

    def _handle_trades(self) -> SkillResponse:
        """Return recent gaming stock trades by tracked congressional members."""
        db = self._get_db()
        trades = db.get_gaming_trades(days=90, limit=20)
        return self._reply(format_trade_list(trades))

    def _handle_bills(self) -> SkillResponse:
        """Return gambling/gaming-relevant bills above the relevance threshold."""
        db = self._get_db()
        bills = db.get_relevant_bills(min_score=0.4, limit=20)
        return self._reply(format_bill_list(bills))

    def _handle_profile(self, name_query: str) -> SkillResponse:
        """Return full intelligence profile for a searched politician."""
        db = self._get_db()
        politicians = db.search_politicians(name_query)
        if not politicians:
            return self._error(
                f"No tracked politician found matching '{name_query}'.\n"
                "Use 'congressman', 'senator', or full last name."
            )
        # Use the first match
        politician = politicians[0]
        trades = db.get_trades_by_politician(politician["id"], limit=10)
        alerts = db.get_recent_alerts(days=30, limit=5)
        alerts = [a for a in alerts if a["politician_id"] == politician["id"]]
        return self._reply(format_politician_profile(politician, trades, alerts))

    def _handle_briefing(self) -> SkillResponse:
        """Return a daily intelligence briefing across all categories."""
        db = self._get_db()
        alerts = db.get_recent_alerts(days=1, limit=20)
        trades = db.get_gaming_trades(days=7, limit=10)
        bills = db.get_relevant_bills(min_score=0.5, limit=10)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._reply(format_briefing(today, alerts, trades, bills))
