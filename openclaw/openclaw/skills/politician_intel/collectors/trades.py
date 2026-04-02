"""STOCK Act trade disclosure collector — v0.1 skeleton.

Fetches congressional stock trade disclosures from two sources:
    1. Senate eFD (Electronic Financial Disclosures): efts.us.senate.gov
       — Search API returns JSON; individual filings are PDFs
    2. House Financial Disclosures: disclosures.house.gov
       — JS-rendered site, requires playwright for scraping

Both sources are free with no API key required.

Key library: pdfplumber for extracting tables from Senate eFD PDFs.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_SENATE_EFD_SEARCH = "https://efts.us.senate.gov/LATEST/search-index"
_SENATE_EFD_BASE   = "https://efts.us.senate.gov"
_HOUSE_DISCLOSURES = "https://disclosures.house.gov/FinancialDisclosure"

# Gaming tickers to flag automatically
GAMING_TICKERS = {
    "DKNG", "PENN", "MGM", "CZR", "FLUT", "CHDN",
    "WYNN", "LVS", "BYD", "RSI", "GDEN", "EVRI",
    "BALY", "GAN", "SRAD",
}


class TradesCollector:
    """Fetches and parses STOCK Act trade disclosures from Senate eFD and House.

    Flow:
        Senate: search_senate_efd() -> returns filing metadata with PDF links
                parse_trade_pdf()   -> downloads PDF, extracts trade table rows
        House:  fetch_house_disclosures() -> playwright scrape, returns trade rows directly
    """

    def __init__(self, db: Any, http_client: Any | None = None) -> None:
        """Initialise the collector.

        Args:
            db: PoliticianDB instance for storing parsed trades.
            http_client: Optional pre-configured httpx.AsyncClient.
        """
        self._db = db
        self._http = http_client

    # ── Public methods ────────────────────────────────────

    async def search_senate_efd(
        self,
        first_name: str | None = None,
        last_name: str | None = None,
        report_types: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search the Senate eFD API for financial disclosure filings.

        Calls the search API at efts.us.senate.gov/LATEST/search-index.
        Returns metadata including report_title, date_filed, and a link to
        the filing PDF. Does NOT download or parse PDFs — call parse_trade_pdf()
        for each result.

        Args:
            first_name: Filer first name filter (partial match supported).
            last_name: Filer last name filter (partial match supported).
            report_types: List of report type strings, e.g. ['Annual', 'Periodic Transaction'].
                          Default: ['Periodic Transaction Report'] (trade-specific filings).
            date_from: Start date filter in YYYY-MM-DD format.
            date_to: End date filter in YYYY-MM-DD format.

        Returns:
            List of filing metadata dicts with keys: name, report_title, date_filed, pdf_url.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "TradesCollector.search_senate_efd() — not yet implemented. "
            "Will POST to efts.us.senate.gov/LATEST/search-index, paginate results, "
            "return metadata list including pdf_url for each filing."
        )

    async def parse_trade_pdf(
        self,
        pdf_url: str,
        politician_id: int,
    ) -> list[dict[str, Any]]:
        """Download a Senate eFD filing PDF and extract trade rows.

        Downloads the PDF from the given URL, uses pdfplumber to find the
        Periodic Transaction Report table, and parses each row into a trade
        dict. Flags GAMING_TICKERS automatically and calls db.store_trade().

        Expected table columns:
            Asset Name | Asset Type | Transaction Type | Amount | Filed | Traded

        Args:
            pdf_url: Full URL to the eFD filing PDF.
            politician_id: ID of the politician in the politicians table.

        Returns:
            List of parsed trade dicts (before DB storage).

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "TradesCollector.parse_trade_pdf() — not yet implemented. "
            "Will use pdfplumber to extract tables from the filing PDF, "
            "parse amount_range and traded_date, flag is_gaming_stock, "
            "and call db.store_trade() for each row."
        )

    async def fetch_house_disclosures(
        self,
        last_name: str | None = None,
        filing_year: int | None = None,
    ) -> list[dict[str, Any]]:
        """Scrape trade disclosures from the House Financial Disclosures site.

        The House disclosure site is JavaScript-rendered and requires a headless
        browser. Uses playwright with chromium in headless mode to:
            1. Navigate to disclosures.house.gov/FinancialDisclosure
            2. Search for the member by last name / year
            3. Extract the filing table rows from the rendered DOM
            4. Download and parse each Periodic Transaction Report PDF

        This is the hardest scraper due to anti-bot protections and JS rendering.
        Implement after Senate eFD is working.

        Args:
            last_name: Member last name filter.
            filing_year: Filing year filter.

        Returns:
            List of parsed trade dicts.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "TradesCollector.fetch_house_disclosures() — not yet implemented. "
            "Requires playwright (pip install playwright && playwright install chromium). "
            "Most complex scraper — implement Week 4 Day 1."
        )

    # ── Private helpers ───────────────────────────────────

    def _parse_amount_range(self, amount_str: str) -> tuple[float | None, float | None]:
        """Parse an eFD amount range string into (min, max) floats.

        Example input: '$1,001 - $15,000' -> (1001.0, 15000.0)

        Args:
            amount_str: Raw amount range string from the filing.

        Returns:
            Tuple of (amount_min, amount_max), either may be None if unparseable.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "TradesCollector._parse_amount_range() — not yet implemented. "
            "Will strip '$', commas, and split on ' - ' to get min/max floats."
        )

    def _is_gaming_ticker(self, ticker: str) -> bool:
        """Return True if the ticker is in the GAMING_TICKERS set."""
        return ticker.upper().strip() in GAMING_TICKERS
