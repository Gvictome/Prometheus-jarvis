"""Senate LDA lobbying registration collector — v0.1 skeleton.

Fetches lobbying disclosure data from the Senate's Lobbying Disclosure Act
database via the public REST API at lda.senate.gov/api/.

No authentication required. Free, no rate limiting documented.
Data is filed quarterly; most relevant for identifying which corporations
are lobbying which congressional offices on gambling/gaming issues.

Base URL: https://lda.senate.gov/api/v1/
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_LDA_BASE = "https://lda.senate.gov/api/v1"

# Gambling/gaming-related issue area codes in the LDA system
GAMBLING_ISSUE_CODES = [
    "GAM",  # Gambling/Lotteries
    "SPO",  # Sports (for stadium/franchise legislation)
    "TAX",  # Tax issues affecting gaming operators
    "TOR",  # Torts/Consumer Protection (online gambling regs)
]

# Client/registrant name keywords for gambling industry
GAMBLING_CLIENT_KEYWORDS = [
    "casino", "gaming", "lottery", "draft kings", "draftkings", "penn national",
    "mgm resorts", "caesars", "fanduel", "flutter", "betmgm", "wynn",
    "american gaming association", "aga", "sports betting", "igaming",
]


class LobbyingCollector:
    """Fetches and stores lobbying registration data from the Senate LDA API.

    The LDA API uses cursor-based pagination. Each filing includes:
        - registrant (the lobbying firm)
        - client (who hired the firm)
        - lobbyists (individual lobbyist names)
        - covered_officials (who was lobbied — members, staff, agencies)
        - lobbying_activities (issue codes + description)
        - income / expenses
    """

    def __init__(self, db: Any, http_client: Any | None = None) -> None:
        """Initialise the collector.

        Args:
            db: PoliticianDB instance for storing lobbying contact data.
            http_client: Optional pre-configured httpx.AsyncClient.
        """
        self._db = db
        self._http = http_client

    # ── Public methods ────────────────────────────────────

    async def fetch_senate_lda(
        self,
        filing_year: int | None = None,
        filing_period: str | None = None,
        issue_codes: list[str] | None = None,
        client_keywords: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch lobbying filings from the Senate LDA API and store relevant records.

        Searches for filings matching gambling-related issue codes or client names.
        For each matching filing, cross-references covered_officials against the
        politicians table to create lobbying_contacts records.

        Endpoint: GET /api/v1/filings/
        Supports filters: filing_year, filing_period, registrant_name,
                          lobbyist_name, issue_code, filing_type.

        Args:
            filing_year: Year to filter on (e.g., 2024). None = all years.
            filing_period: 'Q1', 'Q2', 'Q3', 'Q4', 'mid-year', 'year-end'.
                           None = all periods.
            issue_codes: LDA issue area codes to filter. Defaults to GAMBLING_ISSUE_CODES.
            client_keywords: Client name keywords to match. Defaults to GAMBLING_CLIENT_KEYWORDS.

        Returns:
            List of stored lobbying contact dicts.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "LobbyingCollector.fetch_senate_lda() — not yet implemented. "
            "Will call GET /api/v1/filings/ with issue_code filters, paginate results, "
            "match covered_officials to politicians table, store via db.store_lobbying()."
        )

    # ── Private helpers ───────────────────────────────────

    async def _get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request to the Senate LDA API.

        No auth required. Handles cursor-based pagination via 'next' field
        in the response.

        Args:
            endpoint: API path (e.g., '/filings/').
            params: Query parameters.

        Returns:
            Parsed JSON response dict.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "LobbyingCollector._get() — not yet implemented."
        )

    def _is_gambling_client(self, client_name: str) -> bool:
        """Return True if the client name matches any gambling industry keyword."""
        lower = client_name.lower()
        return any(kw in lower for kw in GAMBLING_CLIENT_KEYWORDS)

    def _match_official_to_politician(
        self,
        official_name: str,
    ) -> int | None:
        """Attempt to match a covered_official name to a politician ID in the DB.

        Searches the politicians table by name (fuzzy match).
        Returns the politician_id if found, None otherwise.

        Args:
            official_name: Raw covered official name from the LDA filing.

        Returns:
            politician_id integer, or None if no match found.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "LobbyingCollector._match_official_to_politician() — not yet implemented. "
            "Will call db.search_politicians(official_name) and return first match id."
        )
