"""Campaign finance collector — v0.1 skeleton.

Fetches donation data from two free sources:
    1. OpenSecrets API  — industry-level and PAC-level donations, career totals
       Base URL: https://www.opensecrets.org/api/
       Auth: Free API key (OPENSECRETS_API_KEY env var)

    2. FEC API          — individual contribution records, committee totals
       Base URL: https://api.open.fec.gov/v1/
       Auth: Free API key (FEC_API_KEY env var)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_OPENSECRETS_BASE = "https://www.opensecrets.org/api/"
_FEC_BASE         = "https://api.open.fec.gov/v1"

_OPENSECRETS_KEY = os.getenv("OPENSECRETS_API_KEY", "")
_FEC_KEY         = os.getenv("FEC_API_KEY", "")

# Industries to track from OpenSecrets
TARGET_INDUSTRIES = [
    "Gambling & Casinos",
    "Recreation/Live Entertainment",
    "Sports & Recreation",
    "TV/Movies/Music",
    "Hotels & Motels",
    "Real Estate",        # stadium funding
]


class FinanceCollector:
    """Fetches and stores campaign finance data from OpenSecrets and FEC.

    Both APIs are free with self-service key registration.
    OpenSecrets rate limit: 200 requests/day on free tier.
    FEC rate limit: 1,000 requests/hour on free tier.
    """

    def __init__(self, db: Any, http_client: Any | None = None) -> None:
        """Initialise the collector.

        Args:
            db: PoliticianDB instance for storing finance data.
            http_client: Optional pre-configured httpx.AsyncClient.
        """
        self._db = db
        self._http = http_client
        if not _OPENSECRETS_KEY:
            logger.warning(
                "OPENSECRETS_API_KEY not set. Get a free key at "
                "https://www.opensecrets.org/open-data/api"
            )
        if not _FEC_KEY:
            logger.warning(
                "FEC_API_KEY not set. Get a free key at "
                "https://api.open.fec.gov/developers/"
            )

    # ── Public methods ────────────────────────────────────

    async def fetch_opensecrets(
        self,
        cid: str,
        cycle: int | None = None,
    ) -> dict[str, Any]:
        """Fetch industry and PAC donation breakdown for a member from OpenSecrets.

        Calls the /candSector and /candContrib endpoints to get:
            - Total donations by industry (TARGET_INDUSTRIES filter)
            - Top PAC contributors by name and amount

        Stores results via db.upsert_finance() for each industry row.

        Args:
            cid: OpenSecrets candidate ID (e.g., 'N00007360' for Pelosi).
                 Note: Different from Congress.gov bioguide_id — requires mapping.
            cycle: Election cycle year (e.g., 2024). None = most recent.

        Returns:
            Dict with keys 'industries' and 'pacs', each a list of dicts.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "FinanceCollector.fetch_opensecrets() — not yet implemented. "
            "Will call /candSector?cid={cid}&cycle={cycle} and /candContrib, "
            "filter to TARGET_INDUSTRIES, store via db.upsert_finance()."
        )

    async def fetch_fec(
        self,
        candidate_id: str,
        cycle: int | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch committee-level donation totals from the FEC API.

        Calls GET /v1/candidate/{candidate_id}/totals/ for aggregate totals,
        and GET /v1/schedules/schedule_b/ for disbursements if needed.

        Focuses on receipts from gambling/gaming industry PACs identified by
        matching committee names against GAMING_PAC_KEYWORDS.

        Args:
            candidate_id: FEC candidate ID (e.g., 'P00000001').
                          Different from bioguide_id and OpenSecrets cid.
            cycle: Election cycle year. None = all cycles.
            per_page: Results per API page.

        Returns:
            List of donation records with committee name, amount, cycle.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "FinanceCollector.fetch_fec() — not yet implemented. "
            "Will call /v1/candidate/{candidate_id}/totals/, filter to "
            "gambling/gaming PACs by name, store via db.upsert_finance()."
        )

    # ── Private helpers ───────────────────────────────────

    async def _opensecrets_get(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Make an authenticated GET request to the OpenSecrets API.

        Appends output=json and apikey to params automatically.

        Args:
            method: OpenSecrets API method name (e.g., 'candSector').
            params: Additional query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "FinanceCollector._opensecrets_get() — not yet implemented."
        )

    async def _fec_get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated GET request to the FEC API.

        Appends api_key to params automatically.

        Args:
            endpoint: FEC API path (e.g., '/candidate/P000001/totals/').
            params: Additional query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "FinanceCollector._fec_get() — not yet implemented."
        )
