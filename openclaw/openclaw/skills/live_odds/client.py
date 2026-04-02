"""The Odds API client — live sports odds fetcher.

Uses The Odds API (https://the-odds-api.com) to fetch real-time odds
across multiple bookmakers. API key required via ODDS_API_KEY env var.

Rate limits tracked via x-requests-remaining header.
Free tier: 500 requests/month. Warns when below 50 remaining.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("ODDS_API_KEY", "")
_BASE_URL = "https://api.the-odds-api.com/v4"

# Warn threshold for remaining requests
_WARN_REMAINING = 50


class OddsClient:
    """Client for The Odds API.

    All methods return raw API response dicts. The caller is responsible
    for storing and processing the data.

    Usage:
        client = OddsClient()
        sports = await client.get_sports()
        odds = await client.get_odds("basketball_nba")
    """

    def __init__(
        self,
        api_key: str | None = None,
        http_client: Any | None = None,
    ) -> None:
        self._api_key = api_key or _API_KEY
        self._http = http_client
        self._requests_remaining: int | None = None
        self._requests_used: int | None = None

        if not self._api_key:
            logger.warning(
                "ODDS_API_KEY not set — live odds requests will fail. "
                "Get a free key at https://the-odds-api.com/"
            )

    @property
    def is_available(self) -> bool:
        """Return True if an API key is configured."""
        return bool(self._api_key)

    @property
    def requests_remaining(self) -> int | None:
        """Last known x-requests-remaining value, or None if not yet fetched."""
        return self._requests_remaining

    async def get_sports(self, all_sports: bool = False) -> list[dict[str, Any]]:
        """Return list of in-season sports.

        Args:
            all_sports: If True, include out-of-season sports.

        Returns:
            List of sport dicts with keys: key, title, active, has_outrights.
        """
        params: dict[str, Any] = {"all": "true" if all_sports else "false"}
        data = await self._get("/sports", params)
        return data if isinstance(data, list) else []

    async def get_odds(
        self,
        sport: str,
        regions: str = "us",
        markets: str = "h2h,spreads,totals",
        bookmakers: str | None = None,
        odds_format: str = "american",
    ) -> list[dict[str, Any]]:
        """Return live odds for a sport.

        Args:
            sport: Sport key, e.g. 'basketball_nba', 'americanfootball_nfl'.
            regions: Comma-separated region codes: 'us', 'uk', 'eu', 'au'.
            markets: Comma-separated market types: 'h2h', 'spreads', 'totals'.
            bookmakers: Optional comma-separated bookmaker keys to filter.
            odds_format: 'american' or 'decimal'.

        Returns:
            List of event dicts with nested bookmaker odds.
        """
        params: dict[str, Any] = {
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
        }
        if bookmakers:
            params["bookmakers"] = bookmakers

        data = await self._get(f"/sports/{sport}/odds", params)
        return data if isinstance(data, list) else []

    async def get_scores(
        self,
        sport: str,
        days_from: int = 1,
    ) -> list[dict[str, Any]]:
        """Return recent scores for a sport.

        Args:
            sport: Sport key, e.g. 'basketball_nba'.
            days_from: Number of days to look back for completed games.

        Returns:
            List of score dicts with home/away scores and completion status.
        """
        params: dict[str, Any] = {"daysFrom": days_from}
        data = await self._get(f"/sports/{sport}/scores", params)
        return data if isinstance(data, list) else []

    # ── Private helpers ───────────────────────────────────

    async def _get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Make an authenticated GET request.

        Tracks x-requests-remaining header and warns when low.

        Args:
            endpoint: API path, e.g. '/sports' (leading slash included).
            params: Query parameters dict (api_key is added automatically).

        Returns:
            Parsed JSON response (list or dict).

        Raises:
            RuntimeError: If httpx is not installed.
            httpx.HTTPStatusError: On non-2xx responses.
        """
        try:
            import httpx
        except ImportError:
            raise RuntimeError(
                "httpx is required for OddsClient. "
                "Add httpx to requirements.txt."
            )

        if not self._api_key:
            raise RuntimeError("ODDS_API_KEY not configured")

        full_params = dict(params or {})
        full_params["apiKey"] = self._api_key

        url = f"{_BASE_URL}{endpoint}"

        try:
            if self._http:
                response = await self._http.get(url, params=full_params)
            else:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.get(url, params=full_params)

            # Track quota headers
            remaining = response.headers.get("x-requests-remaining")
            used = response.headers.get("x-requests-used")
            if remaining is not None:
                self._requests_remaining = int(remaining)
                if self._requests_remaining < _WARN_REMAINING:
                    logger.warning(
                        "OddsClient: only %d API requests remaining this period!",
                        self._requests_remaining,
                    )
            if used is not None:
                self._requests_used = int(used)

            response.raise_for_status()
            return response.json()

        except Exception as exc:
            logger.error("OddsClient._get %s failed: %s", endpoint, exc)
            raise
