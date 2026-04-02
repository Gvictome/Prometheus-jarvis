"""Intel signal engine — v0.1 skeleton.

Generates intelligence alerts by analysing correlations across the
politician_intel database tables. The core value-add of the module:
finding non-obvious connections between political activity and
sports betting market impact.

Alert types:
    gaming_trade      — Member of target committee traded GAMING_TICKERS
    bill_vote         — High-relevance bill vote by tracked committee member
    trade_bill_corr   — Gaming stock trade filed within N days of relevant bill vote
    state_bill        — State-level gambling/betting bill advanced
    finance_signal    — Large gaming PAC donation to committee member
    lobbying_signal   — Gambling industry lobbying contact with key member
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Days window for trade-bill correlation detection
TRADE_BILL_WINDOW_DAYS = 90

# Minimum bill relevance score to trigger an alert
BILL_ALERT_THRESHOLD = 0.5

# Gaming tickers that warrant a 'critical' alert when traded
CRITICAL_TICKERS = {"DKNG", "PENN", "MGM", "CZR", "FLUT"}


class IntelSignalEngine:
    """Analyses politician_intel DB records and generates intel_alerts.

    The engine is designed to run on a cron schedule (see scheduler.py)
    but can also be invoked on-demand from the skill.

    Usage:
        engine = IntelSignalEngine(db)
        new_alerts = await engine.generate_alerts()
    """

    def __init__(self, db: Any) -> None:
        """Initialise the engine.

        Args:
            db: PoliticianDB instance.
        """
        self._db = db

    # ── Public methods ────────────────────────────────────

    async def generate_alerts(self, lookback_days: int = 1) -> list[dict[str, Any]]:
        """Run all alert checks for the lookback window and return new alerts.

        Runs the following checks in sequence:
            1. check_gaming_trades()      — any new gaming stock trades?
            2. check_bill_votes()         — any high-relevance votes?
            3. check_trade_bill_correlation() — trades near bill activity?
            4. check_finance_signals()    — large gaming PAC donations?

        Stores each new alert via db.store_alert() and returns the list.

        Args:
            lookback_days: How many days back to scan for new activity.

        Returns:
            List of newly generated alert dicts (as stored in intel_alerts table).

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "IntelSignalEngine.generate_alerts() — not yet implemented. "
            "Will call each check_* method, aggregate results, de-duplicate "
            "against existing alerts, store via db.store_alert()."
        )

    async def check_gaming_trades(
        self,
        lookback_days: int = 1,
    ) -> list[dict[str, Any]]:
        """Check for new gaming stock trades by tracked committee members.

        Queries stock_trades where is_gaming_stock=1 and filed_date is within
        lookback_days. Cross-references politician's committee assignments
        to determine severity:
            - TARGET_COMMITTEES member + CRITICAL_TICKERS ticker = 'critical'
            - TARGET_COMMITTEES member + other gaming ticker    = 'high'
            - Non-committee member + any gaming ticker          = 'medium'

        Args:
            lookback_days: Days back to scan.

        Returns:
            List of alert dicts to store (not yet stored).

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "IntelSignalEngine.check_gaming_trades() — not yet implemented. "
            "Will query db.get_gaming_trades(days=lookback_days), determine severity "
            "by committee membership, return alert dicts."
        )

    async def check_bill_votes(
        self,
        lookback_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Check for votes on high-relevance bills by tracked committee members.

        Queries votes table where relevance_score >= BILL_ALERT_THRESHOLD and
        voted_at is within lookback_days. Severity is proportional to
        relevance_score and committee membership.

        Args:
            lookback_days: Days back to scan.

        Returns:
            List of alert dicts to store.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "IntelSignalEngine.check_bill_votes() — not yet implemented."
        )

    async def check_trade_bill_correlation(
        self,
        window_days: int = TRADE_BILL_WINDOW_DAYS,
    ) -> list[dict[str, Any]]:
        """Detect gaming stock trades that occurred near a related bill vote.

        The core correlation signal: a politician traded a gaming stock within
        TRADE_BILL_WINDOW_DAYS before or after voting on gambling-related legislation.

        Logic:
            For each gaming trade by a committee member:
                Find votes by the same politician on gambling bills
                where abs(trade_date - vote_date) <= window_days
            Generate 'critical' alert if correlation found.

        Args:
            window_days: Days window for correlation detection.

        Returns:
            List of alert dicts to store.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "IntelSignalEngine.check_trade_bill_correlation() — not yet implemented. "
            "Will join stock_trades with votes on politician_id, compute date delta, "
            "generate critical alerts for correlations within window_days."
        )

    async def check_finance_signals(
        self,
        lookback_days: int = 30,
        threshold_amount: float = 10_000.0,
    ) -> list[dict[str, Any]]:
        """Check for large gaming PAC donations to tracked committee members.

        Queries campaign_finance for gaming/gambling industry rows above
        threshold_amount for tracked politicians on TARGET_COMMITTEES.

        Args:
            lookback_days: Days since updated_at to consider recent.
            threshold_amount: Minimum total_received to generate an alert.

        Returns:
            List of alert dicts to store.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "IntelSignalEngine.check_finance_signals() — not yet implemented."
        )

    # ── Private helpers ───────────────────────────────────

    def _severity_from_score(self, relevance_score: float, committee_member: bool) -> str:
        """Determine alert severity from relevance score and committee membership.

        Args:
            relevance_score: Bill or trade relevance score [0.0, 1.0].
            committee_member: True if the politician is on a target committee.

        Returns:
            Severity string: 'critical', 'high', 'medium', or 'low'.
        """
        if committee_member and relevance_score >= 0.8:
            return "critical"
        if committee_member and relevance_score >= 0.5:
            return "high"
        if relevance_score >= 0.5:
            return "medium"
        return "low"
