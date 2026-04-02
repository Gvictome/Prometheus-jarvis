"""Sentiment analysis engine — v0.1 skeleton.

Wraps VADER (vaderSentiment) for lightweight, rule-based sentiment scoring
of political statements and press releases. VADER is optimised for short
social-media-style text but performs well on press releases.

Optional upgrade path: FinBERT for financial-domain sentiment when more
precise bearish/bullish classification is needed.

Requires: pip install vadersentiment
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SentimentEngine:
    """Sentiment analysis using VADER, with optional FinBERT upgrade path.

    The engine is lazily initialised — the VADER model loads on first call
    to avoid import-time overhead.

    Usage:
        engine = SentimentEngine()
        score = engine.analyze("DraftKings will transform state revenues positively")
        # Returns 0.72 (positive)
    """

    def __init__(self) -> None:
        self._analyzer: Any | None = None  # vaderSentiment.SentimentIntensityAnalyzer

    def analyze(self, text: str) -> float:
        """Score the sentiment of the given text using VADER compound score.

        The compound score is normalised: -1.0 (most negative) to +1.0 (most positive).
        Thresholds:
            >= 0.05  = positive
            <= -0.05 = negative
            else     = neutral

        Lazily initialises the VADER analyzer on first call.

        Args:
            text: Input text — statement, headline, or press release excerpt.

        Returns:
            VADER compound score as float in [-1.0, 1.0].

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "SentimentEngine.analyze() — not yet implemented. "
            "Will call self._get_analyzer().polarity_scores(text)['compound']."
        )

    def analyze_batch(self, texts: list[str]) -> list[float]:
        """Score sentiment for a list of texts. Returns list of compound scores.

        Args:
            texts: List of text strings to score.

        Returns:
            List of VADER compound scores, same order as input.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "SentimentEngine.analyze_batch() — not yet implemented. "
            "Will call self.analyze() for each text and return the list."
        )

    def label(self, score: float) -> str:
        """Convert a compound score to a human-readable label.

        Args:
            score: VADER compound score in [-1.0, 1.0].

        Returns:
            'positive', 'negative', or 'neutral'.
        """
        if score >= 0.05:
            return "positive"
        if score <= -0.05:
            return "negative"
        return "neutral"

    # ── Private helpers ───────────────────────────────────

    def _get_analyzer(self) -> Any:
        """Lazily initialise and return the VADER SentimentIntensityAnalyzer.

        Returns:
            vaderSentiment.SentimentIntensityAnalyzer instance.

        Raises:
            NotImplementedError: Until this method is fully implemented.
        """
        raise NotImplementedError(
            "SentimentEngine._get_analyzer() — not yet implemented. "
            "Will import vaderSentiment.SentimentIntensityAnalyzer, cache in self._analyzer, "
            "and return it."
        )
