"""Press release and statement collector — v0.1 skeleton.

Fetches member press releases and public statements from:
    1. ProPublica Congress API — /members/{member_id}/statements endpoint
       Base URL: https://api.propublica.org/congress/v1/
       Auth: Free API key (PROPUBLICA_API_KEY env var)

Statement content is scored for relevance (RelevanceScorer) and
sentiment (SentimentEngine) before storage.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_PROPUBLICA_BASE = "https://api.propublica.org/congress/v1"
_PROPUBLICA_KEY = os.getenv("PROPUBLICA_API_KEY", "")


class StatementsCollector:
    """Fetches press releases and statements, scores sentiment and relevance.

    Flow:
        fetch_propublica_statements() -> raw statement list
        analyze_sentiment()           -> adds sentiment_score to each statement
        relevance scorer              -> filters to gambling/sports/stadium content
        db.store_statement()          -> persists relevant statements
    """

    def __init__(self, db: Any, http_client: Any | None = None) -> None:
        """Initialise the collector.

        Args:
            db: PoliticianDB instance for storing statement data.
            http_client: Optional pre-configured httpx.AsyncClient.
        """
        self._db = db
        self._http = http_client
        if not _PROPUBLICA_KEY:
            logger.warning(
                "PROPUBLICA_API_KEY not set. Get a free key at "
                "https://www.propublica.org/datastore/api/propublica-congress-api"
            )

    # ── Public methods ────────────────────────────────────

    async def fetch_propublica_statements(
        self,
        bioguide_id: str,
        subject: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch press releases and statements for a member from ProPublica.

        Calls GET /members/{member_id}/statements[/{congress}/{subject}].
        Optionally filters by subject slug.

        Each returned statement includes:
            - statement_type ('press-release', 'floor-statement', 'committee-statement')
            - title, url, date
            - subjects (list of ProPublica subject slugs)

        Note: ProPublica returns titles and URLs only — full text requires
        scraping the linked page. Implement full text fetch as optional
        enhancement (Week 3).

        Args:
            bioguide_id: Congress.gov BioGuide ID (same as used in politicians table).
            subject: ProPublica subject slug filter, e.g. 'gambling'. None = all.

        Returns:
            List of statement dicts with relevance and sentiment scores attached.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "StatementsCollector.fetch_propublica_statements() — not yet implemented. "
            "Will call GET /members/{bioguide_id}/statements, score relevance "
            "and sentiment, store via db.store_statement()."
        )

    def analyze_sentiment(self, text: str) -> float:
        """Score sentiment of a text string using VADER.

        Returns the VADER compound score: -1.0 (most negative) to +1.0 (most positive).
        0.0 is neutral. Threshold for positive: >= 0.05; negative: <= -0.05.

        Requires: pip install vadersentiment

        Args:
            text: Statement or press release text to analyse.

        Returns:
            VADER compound sentiment score as float.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "StatementsCollector.analyze_sentiment() — not yet implemented. "
            "Will use vaderSentiment.SentimentIntensityAnalyzer().polarity_scores(text)['compound']."
        )

    # ── Private helpers ───────────────────────────────────

    async def _propublica_get(
        self,
        endpoint: str,
    ) -> dict[str, Any]:
        """Make an authenticated GET request to the ProPublica Congress API.

        Appends X-API-Key header automatically.

        Args:
            endpoint: API path (e.g., '/members/P000197/statements.json').

        Returns:
            Parsed JSON response.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "StatementsCollector._propublica_get() — not yet implemented."
        )
