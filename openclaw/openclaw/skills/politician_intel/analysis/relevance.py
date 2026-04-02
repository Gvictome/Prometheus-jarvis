"""Relevance scoring engine — v0.2

Scores bills and statements for relevance to gambling, sports betting,
stadium funding, and gaming industry topics. Returns a float 0.0-1.0.

Used by collectors before storing to the DB, and by the signal engine
to prioritise alert generation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Keyword lists ──────────────────────────────────────────
# Scored by tier: TIER_1 = high signal, TIER_2 = medium, TIER_3 = context

GAMBLING_KEYWORDS_T1 = [
    "sports betting", "online gambling", "igaming", "i-gaming",
    "sports wagering", "mobile betting", "single-game betting",
    "gambling legalization", "legalize gambling", "gaming license",
    "sports book", "sportsbook", "daily fantasy sports", "dfs",
    "draftkings", "fanduel", "penn gaming", "caesars entertainment",
    "mgm resorts", "betmgm", "pointsbet", "bet365",
]

GAMBLING_KEYWORDS_T2 = [
    "casino", "lottery", "gambling", "gaming", "wager", "wagering",
    "bettor", "betting", "poker", "slots", "roulette", "blackjack",
    "tribal gaming", "indian gaming", "igra", "native american gaming",
    "offshore betting", "illegal gambling", "wire act", "uigea",
    "professional gambling", "gambling addiction", "problem gambling",
    "responsible gaming",
]

STADIUM_KEYWORDS_T1 = [
    "stadium funding", "arena funding", "stadium construction",
    "sports complex", "stadium bond", "stadium tax",
    "public financing stadium", "stadium subsidy",
    "nfl stadium", "nba arena", "mlb stadium", "nhl arena",
]

STADIUM_KEYWORDS_T2 = [
    "stadium", "arena", "ballpark", "sports venue", "franchise",
    "relocation", "expansion team", "host city",
]

SPORTS_KEYWORDS_T2 = [
    "professional sports", "sports league", "athlete", "nfl", "nba",
    "mlb", "nhl", "mls", "ncaa", "college sports", "sports team",
    "sports franchise", "sports entertainment",
]

REGULATORY_KEYWORDS_T2 = [
    "gaming commission", "gaming control board", "gaming regulation",
    "gambling regulation", "gambling tax", "gaming tax", "excise tax",
    "consumer protection gambling", "advertising gambling",
]

# Category thresholds
CATEGORY_MAP = {
    "gambling": 0.3,
    "sports":   0.2,
    "stadium":  0.2,
    "finance":  0.15,  # campaign finance/PAC bills
    "other":    0.0,
}


class RelevanceScorer:
    """Scores text content for gambling/sports/stadium relevance.

    Scoring algorithm:
        1. Tokenize and lowercase input text
        2. Check for TIER_1 keywords (weight 0.4 each, max 1.0)
        3. Check for TIER_2 keywords (weight 0.15 each, max 0.6)
        4. Apply context boost if multiple categories hit
        5. Clamp to [0.0, 1.0]

    The scorer is stateless and can be used as a singleton.
    """

    def score_bill(
        self,
        title: str,
        summary: str | None = None,
        subjects: list[str] | None = None,
    ) -> tuple[float, str]:
        """Score a bill for gambling/sports/stadium relevance.

        Title is weighted 2x vs summary (titles are more signal-dense).
        ProPublica subject tags are treated as TIER_1 keywords.

        Args:
            title: Bill title (short name), e.g. 'Sports Betting Consumer Protection Act'.
            summary: Optional full bill summary text.
            subjects: Optional list of subject/tag strings from the API.

        Returns:
            Tuple of (relevance_score: float, category: str).
            category is the highest-scoring category, or 'other' if below threshold.
        """
        # Build search corpus — title at 2x weight
        title_text = (title or "").lower()
        summary_text = (summary or "").lower()
        subjects_text = " ".join(subjects or []).lower()

        # Combined text: title repeated twice + summary + subjects
        full_text = f"{title_text} {title_text} {summary_text} {subjects_text}"

        # Category score accumulators
        gambling_score = 0.0
        stadium_score = 0.0
        sports_score = 0.0

        # TIER_1 keywords: 0.4 weight each
        gambling_t1_hits = self._count_keywords(full_text, GAMBLING_KEYWORDS_T1)
        gambling_score += min(gambling_t1_hits * 0.4, 1.0)

        stadium_t1_hits = self._count_keywords(full_text, STADIUM_KEYWORDS_T1)
        stadium_score += min(stadium_t1_hits * 0.4, 1.0)

        # Subject tags as TIER_1 (ProPublica subjects are pre-classified)
        if subjects:
            for subj in subjects:
                subj_lower = subj.lower()
                if any(kw in subj_lower for kw in ["gambling", "gaming", "betting", "lottery"]):
                    gambling_score += 0.4
                if any(kw in subj_lower for kw in ["stadium", "arena", "sports venue"]):
                    stadium_score += 0.4
                if any(kw in subj_lower for kw in ["sports", "athletics", "nfl", "nba", "mlb"]):
                    sports_score += 0.2

        # TIER_2 keywords: 0.15 weight each
        gambling_t2_hits = self._count_keywords(full_text, GAMBLING_KEYWORDS_T2)
        gambling_score += min(gambling_t2_hits * 0.15, 0.6)

        stadium_t2_hits = self._count_keywords(full_text, STADIUM_KEYWORDS_T2)
        stadium_score += min(stadium_t2_hits * 0.15, 0.6)

        sports_t2_hits = self._count_keywords(full_text, SPORTS_KEYWORDS_T2)
        sports_score += min(sports_t2_hits * 0.15, 0.6)

        regulatory_hits = self._count_keywords(full_text, REGULATORY_KEYWORDS_T2)
        gambling_score += min(regulatory_hits * 0.1, 0.3)

        # Multi-category context boost
        categories_hit = sum([
            gambling_score > 0.1,
            stadium_score > 0.1,
            sports_score > 0.1,
        ])
        if categories_hit >= 2:
            gambling_score *= 1.2
            stadium_score *= 1.2

        scores = {
            "gambling": min(gambling_score, 1.0),
            "stadium": min(stadium_score, 1.0),
            "sports": min(sports_score, 1.0),
        }

        category = self._determine_category(scores)
        final_score = max(scores.values()) if scores else 0.0
        final_score = min(final_score, 1.0)

        logger.debug(
            "score_bill title=%r scores=%s -> %.3f %s",
            title[:60], scores, final_score, category,
        )
        return final_score, category

    def score_statement(
        self,
        content: str,
        source: str | None = None,
    ) -> tuple[float, str]:
        """Score a press release or floor statement for relevance.

        Floor statements get 1.5x multiplier — they are more direct signals
        than generic press releases.

        Args:
            content: Full text of the statement or title if full text unavailable.
            source: Statement source type for context ('press-release', 'floor-statement').

        Returns:
            Tuple of (relevance_score: float, category: str).
        """
        text = (content or "").lower()

        gambling_score = 0.0
        stadium_score = 0.0
        sports_score = 0.0

        # TIER_1 keywords: 0.4 weight
        gambling_t1 = self._count_keywords(text, GAMBLING_KEYWORDS_T1)
        gambling_score += min(gambling_t1 * 0.4, 1.0)

        stadium_t1 = self._count_keywords(text, STADIUM_KEYWORDS_T1)
        stadium_score += min(stadium_t1 * 0.4, 1.0)

        # TIER_2 keywords: 0.15 weight
        gambling_t2 = self._count_keywords(text, GAMBLING_KEYWORDS_T2)
        gambling_score += min(gambling_t2 * 0.15, 0.6)

        stadium_t2 = self._count_keywords(text, STADIUM_KEYWORDS_T2)
        stadium_score += min(stadium_t2 * 0.15, 0.6)

        sports_t2 = self._count_keywords(text, SPORTS_KEYWORDS_T2)
        sports_score += min(sports_t2 * 0.15, 0.6)

        regulatory = self._count_keywords(text, REGULATORY_KEYWORDS_T2)
        gambling_score += min(regulatory * 0.1, 0.3)

        # Floor statements: 1.5x multiplier (more direct signal)
        if source and "floor" in source.lower():
            gambling_score *= 1.5
            stadium_score *= 1.5
            sports_score *= 1.5

        scores = {
            "gambling": min(gambling_score, 1.0),
            "stadium": min(stadium_score, 1.0),
            "sports": min(sports_score, 1.0),
        }

        category = self._determine_category(scores)
        final_score = max(scores.values()) if scores else 0.0
        final_score = min(final_score, 1.0)

        logger.debug(
            "score_statement source=%s -> %.3f %s", source, final_score, category
        )
        return final_score, category

    # ── Private helpers ───────────────────────────────────

    def _count_keywords(
        self,
        text: str,
        keywords: list[str],
    ) -> int:
        """Count how many keywords from the list appear in the text.

        Case-insensitive, word-boundary-aware matching.

        Args:
            text: Input text (should be pre-lowercased for performance).
            keywords: List of keyword strings to match.

        Returns:
            Count of matching keywords.
        """
        text_lower = text.lower()
        count = 0
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text_lower):
                count += 1
        return count

    def _determine_category(self, scores: dict[str, float]) -> str:
        """Return the category with the highest score, or 'other' if all are below threshold.

        Args:
            scores: Dict mapping category names to their raw scores.

        Returns:
            Category name string.
        """
        if not scores:
            return "other"
        best = max(scores.items(), key=lambda x: x[1])
        if best[1] >= CATEGORY_MAP.get(best[0], 0.0):
            return best[0]
        return "other"
