"""Gateway middleware: authentication, rate limiting, audit logging."""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from openclaw.config import settings
from openclaw.gateway.schemas import Channel, UnifiedMessage
from openclaw.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """User authentication and tier assignment."""

    def __init__(self, store: MemoryStore):
        self.store = store
        self.admin_ids = set(settings.ADMIN_USER_IDS)

    def get_user_tier(self, sender_id: str) -> int:
        """Get user's access tier. Admins are T5, API users T1, others T0."""
        if sender_id in self.admin_ids:
            return 5
        # Default: allow basic access for recognized channels
        return 1

    def is_authorized(self, message: UnifiedMessage, required_tier: int) -> bool:
        tier = self.get_user_tier(message.sender_id)
        if tier < required_tier:
            self.store.log_audit(
                user_id=message.sender_id,
                action="access_denied",
                detail=f"Required tier {required_tier}, has tier {tier}",
                tier=tier,
            )
            return False
        return True


class RateLimiter:
    """Simple in-memory rate limiter per sender."""

    def __init__(self, max_per_minute: int = 30, max_per_hour: int = 200):
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self._minute_counts: dict[str, list[float]] = defaultdict(list)
        self._hour_counts: dict[str, list[float]] = defaultdict(list)

    def check(self, sender_id: str) -> bool:
        """Returns True if request is allowed."""
        now = time.time()

        # Clean old entries and check minute limit
        minute_ago = now - 60
        self._minute_counts[sender_id] = [
            t for t in self._minute_counts[sender_id] if t > minute_ago
        ]
        if len(self._minute_counts[sender_id]) >= self.max_per_minute:
            return False

        # Check hour limit
        hour_ago = now - 3600
        self._hour_counts[sender_id] = [
            t for t in self._hour_counts[sender_id] if t > hour_ago
        ]
        if len(self._hour_counts[sender_id]) >= self.max_per_hour:
            return False

        self._minute_counts[sender_id].append(now)
        self._hour_counts[sender_id].append(now)
        return True
