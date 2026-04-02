"""Gateway middleware: authentication, rate limiting, audit logging.

Tier system:
  T0 — anonymous / unauthenticated (no access to gated skills)
  T1 — standard authenticated user (basic skills: conversation, briefing, search)
  T2 — trusted user (smart home, sports signals)
  T3 — power user (system read-only: disk, memory, docker ps)
  T4 — elevated (write operations: service restart, docker restart)
  T5 — admin (full access: overseer, security audit, SSH hardening)

ADMIN_USER_IDS → T5.
TRUSTED_USER_IDS → T2.
All other authenticated senders → T1.
Unauthenticated (sender_id == "anonymous") → T0.
"""

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
        # T2 trusted users can be configured via TRUSTED_USER_IDS env var
        self.trusted_ids: set[str] = set(getattr(settings, "TRUSTED_USER_IDS", []))

    def get_user_tier(self, sender_id: str) -> int:
        """Get user's access tier.

        Returns:
            5 for admins, 2 for trusted users, 1 for all other authenticated
            senders, 0 for anonymous.
        """
        if sender_id in self.admin_ids:
            return 5
        if sender_id in self.trusted_ids:
            return 2
        if not sender_id or sender_id == "anonymous":
            return 0
        # All other identified senders (Telegram/WhatsApp users) get basic access
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
    """Rate limiter per sender, backed by Redis with in-memory fallback.

    Uses Redis sliding-window counters when available so limits are shared
    across all openclaw instances (important for the team deploy).  Falls
    back to in-memory lists if Redis is unavailable.
    """

    def __init__(self, max_per_minute: int = 30, max_per_hour: int = 200):
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self._redis = None
        self._minute_counts: dict[str, list[float]] = defaultdict(list)
        self._hour_counts: dict[str, list[float]] = defaultdict(list)
        self._init_redis()

    def _init_redis(self) -> None:
        try:
            import redis as redis_lib
            self._redis = redis_lib.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._redis.ping()
            logger.info("RateLimiter: using Redis at %s", settings.REDIS_URL)
        except Exception as exc:
            logger.warning("RateLimiter: Redis unavailable (%s), using in-memory fallback", exc)
            self._redis = None

    def check(self, sender_id: str) -> bool:
        """Returns True if the request is within rate limits."""
        if self._redis is not None:
            return self._check_redis(sender_id)
        return self._check_memory(sender_id)

    def _check_redis(self, sender_id: str) -> bool:
        """Sliding-window rate check via Redis MULTI/EXEC pipeline."""
        now = time.time()
        pipe = self._redis.pipeline()
        try:
            minute_key = f"rl:min:{sender_id}"
            hour_key = f"rl:hr:{sender_id}"
            minute_ago = now - 60
            hour_ago = now - 3600

            pipe.zremrangebyscore(minute_key, 0, minute_ago)
            pipe.zcard(minute_key)
            pipe.zremrangebyscore(hour_key, 0, hour_ago)
            pipe.zcard(hour_key)
            results = pipe.execute()

            minute_count = results[1]
            hour_count = results[3]

            if minute_count >= self.max_per_minute or hour_count >= self.max_per_hour:
                return False

            pipe2 = self._redis.pipeline()
            pipe2.zadd(minute_key, {str(now): now})
            pipe2.expire(minute_key, 61)
            pipe2.zadd(hour_key, {str(now): now})
            pipe2.expire(hour_key, 3601)
            pipe2.execute()
            return True
        except Exception as exc:
            logger.warning("Redis rate-limit check failed (%s), allowing request", exc)
            return True

    def _check_memory(self, sender_id: str) -> bool:
        """Fallback in-memory sliding window."""
        now = time.time()
        minute_ago = now - 60
        self._minute_counts[sender_id] = [
            t for t in self._minute_counts[sender_id] if t > minute_ago
        ]
        if len(self._minute_counts[sender_id]) >= self.max_per_minute:
            return False
        hour_ago = now - 3600
        self._hour_counts[sender_id] = [
            t for t in self._hour_counts[sender_id] if t > hour_ago
        ]
        if len(self._hour_counts[sender_id]) >= self.max_per_hour:
            return False
        self._minute_counts[sender_id].append(now)
        self._hour_counts[sender_id].append(now)
        return True
