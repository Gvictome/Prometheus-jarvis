"""Sports Signals — Performance tracking and source ranking engine."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Composite score weights — tune as data accumulates
_WEIGHT_WIN_RATE = 0.45
_WEIGHT_ROI = 0.35
_WEIGHT_SAMPLE = 0.20

# Minimum sample size for a source to be considered reliable
_MIN_SAMPLE_SIZE = 10

# Normalisation ceilings used to scale raw values into 0–1
_MAX_ROI_CLAMP = 30.0        # cap ROI at 30 % for scoring purposes
_MAX_SAMPLE_CLAMP = 200.0    # cap sample at 200 picks for scoring purposes


class PerformanceEngine:
    """Calculate and rank source performance metrics."""

    # ── Per-source stats ───────────────────────────────────

    def calculate_source_stats(self, db: Any, source: str) -> dict[str, Any]:
        """Recalculate stats for *source* and persist them.

        Returns the freshly calculated stats dict.
        """
        stats = db.update_source_performance(source)
        stats["reliability"] = self.get_source_reliability(db, source)
        return stats

    # ── Source ranking ─────────────────────────────────────

    def rank_sources(self, db: Any) -> list[dict[str, Any]]:
        """Return all tracked sources ranked by composite score (desc).

        Forces a recalculation for every source so rankings are fresh.
        """
        sources = db.get_all_sources()
        ranked: list[dict[str, Any]] = []

        for source in sources:
            stats = db.update_source_performance(source)
            score = self._composite_score(
                win_rate=stats.get("win_rate", 0.0),
                roi=stats.get("roi", 0.0),
                total_picks=stats.get("total_picks", 0),
            )
            stats["composite_score"] = round(score, 4)
            stats["reliability"] = self.get_source_reliability(db, source)
            ranked.append(stats)

        ranked.sort(key=lambda s: s["composite_score"], reverse=True)
        return ranked

    # ── Reliability score ──────────────────────────────────

    def get_source_reliability(self, db: Any, source: str) -> float:
        """Return a 0.0–1.0 reliability score for a source.

        Accounts for both performance and sample size credibility.
        """
        perf_rows = db.get_source_performance(source)
        if not perf_rows:
            return 0.0

        stats = perf_rows[0]
        total = stats.get("total_picks", 0)
        if total == 0:
            return 0.0

        # Credibility factor — ramps up to 1.0 at _MIN_SAMPLE_SIZE * 5 picks
        credibility = min(1.0, total / (_MIN_SAMPLE_SIZE * 5))

        # Performance component
        perf_score = self._composite_score(
            win_rate=stats.get("win_rate", 0.0),
            roi=stats.get("roi", 0.0),
            total_picks=total,
        )

        return round(credibility * perf_score, 4)

    # ── Internal helpers ───────────────────────────────────

    def _composite_score(
        self,
        win_rate: float,
        roi: float,
        total_picks: int,
    ) -> float:
        """Calculate a composite 0.0–1.0 performance score.

        Blends win rate, ROI, and sample size credibility.
        """
        if total_picks < _MIN_SAMPLE_SIZE:
            # Heavily penalise small samples to avoid overreacting to noise
            credibility_penalty = total_picks / _MIN_SAMPLE_SIZE
        else:
            credibility_penalty = 1.0

        # Normalise win_rate (already 0–1 fraction)
        wr_score = min(1.0, max(0.0, win_rate))

        # Normalise ROI — clamp to [0, _MAX_ROI_CLAMP], negative ROI = 0
        roi_score = min(1.0, max(0.0, roi / _MAX_ROI_CLAMP))

        # Normalise sample size
        sample_score = min(1.0, total_picks / _MAX_SAMPLE_CLAMP)

        raw_score = (
            _WEIGHT_WIN_RATE * wr_score
            + _WEIGHT_ROI * roi_score
            + _WEIGHT_SAMPLE * sample_score
        )

        return round(raw_score * credibility_penalty, 4)

    def is_source_trustworthy(self, db: Any, source: str) -> bool:
        """Quick check: does the source meet minimum quality thresholds?"""
        perf_rows = db.get_source_performance(source)
        if not perf_rows:
            return False
        stats = perf_rows[0]
        return (
            stats.get("total_picks", 0) >= _MIN_SAMPLE_SIZE
            and stats.get("win_rate", 0.0) >= 0.50
        )
