"""Inference cost tracking and budget enforcement."""

from __future__ import annotations

import logging
from typing import Any

from openclaw.config import settings
from openclaw.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class CostTracker:
    def __init__(self, store: MemoryStore):
        self.store = store
        self.monthly_budget = settings.MONTHLY_BUDGET_USD

    def record(self, result: dict[str, Any]):
        """Record an inference call's cost."""
        cost = result.get("cost_usd", 0.0)
        if cost <= 0:
            return

        self.store.log_cost(
            provider=result.get("provider", "unknown"),
            model=result.get("model", "unknown"),
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            cost_usd=cost,
        )
        logger.debug(
            "Cost recorded: $%.6f (%s/%s)",
            cost,
            result.get("provider"),
            result.get("model"),
        )

    def get_monthly_spend(self) -> float:
        return self.store.get_monthly_cost()

    def is_within_budget(self) -> bool:
        return self.get_monthly_spend() < self.monthly_budget

    def get_budget_status(self) -> dict[str, Any]:
        spent = self.get_monthly_spend()
        return {
            "spent_usd": round(spent, 4),
            "budget_usd": self.monthly_budget,
            "remaining_usd": round(self.monthly_budget - spent, 4),
            "utilization_pct": round((spent / self.monthly_budget) * 100, 1)
            if self.monthly_budget > 0
            else 0,
        }
