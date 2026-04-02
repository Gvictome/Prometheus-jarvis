"""Sports Signals — Recommendation engine.

Generates straight bet rankings and low-variance parlay combinations
from today's pending signals, weighted by source performance.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# Straight bet filters
_MIN_WIN_RATE = 0.50        # source must hit > 50 % to be included
_MIN_SAMPLE_SIZE = 5        # minimum graded picks before trusting the source

# Parlay constraints
_MAX_PARLAY_LEGS = 3
_PREFERRED_PARLAY_LEGS = 2
_MIN_LEG_ODDS_DECIMAL = 1.5  # ignore heavy chalk in parlay legs (~-200 or worse)


def _decimal_to_american(decimal_odds: float) -> str:
    """Convert decimal odds to American odds string."""
    if decimal_odds >= 2.0:
        american = int(round((decimal_odds - 1) * 100))
        return f"+{american}"
    else:
        american = int(round(-100 / (decimal_odds - 1)))
        return f"{american}"


def _combine_decimal_odds(legs: list[dict[str, Any]]) -> float:
    """Multiply decimal odds of all legs together to get parlay combined odds."""
    combined = 1.0
    for leg in legs:
        dec = leg.get("odds_decimal") or 1.909  # default ~-110
        combined *= dec
    return round(combined, 4)


def _est_hit_probability(combined_decimal: float) -> float:
    """Estimate the implied probability from combined decimal odds."""
    if combined_decimal <= 0:
        return 0.0
    return round(1.0 / combined_decimal, 4)


def _score_signal(signal: dict[str, Any], source_stats: dict[str, Any]) -> float:
    """Calculate a composite confidence score for a single signal.

    Higher is better. Combines source win rate, ROI, and signal odds value.
    """
    win_rate = source_stats.get("win_rate", 0.0)
    roi = source_stats.get("roi", 0.0)
    total = source_stats.get("total_picks", 0)

    # Sample size credibility ramp (0 → 1 over first 50 picks)
    credibility = min(1.0, total / 50) if total > 0 else 0.0

    # Odds value: slight preference for underdogs (>= +100) — they inflate ROI more
    dec_odds = signal.get("odds_decimal") or 1.909
    odds_bonus = 0.05 if dec_odds >= 2.0 else 0.0

    # Market quality: ML = baseline, spread = slight bonus, prop/total = small penalty
    market = (signal.get("market") or "ML").lower()
    market_adj = {"ml": 0.0, "spread": 0.02, "total": -0.02, "prop": -0.03}.get(market, 0.0)

    raw_score = (
        win_rate * 0.45
        + min(1.0, max(0.0, roi / 30.0)) * 0.35
        + odds_bonus
        + market_adj
    ) * credibility

    return round(raw_score, 4)


class RecommendationEngine:
    """Generate daily straight and parlay recommendations."""

    # ── Straight bets ──────────────────────────────────────

    def generate_straights(
        self,
        db: Any,
        performance_engine: Any,
        max_picks: int = 8,
    ) -> list[dict[str, Any]]:
        """Return today's top straight bets ranked by confidence score.

        Filters by source trustworthiness and deduplicates team exposure.
        Returns at most max_picks.
        """
        pending = db.get_pending_signals()
        if not pending:
            logger.debug("No pending signals for straights")
            return []

        scored: list[dict[str, Any]] = []
        seen_teams: set[str] = set()

        for signal in pending:
            source = signal.get("source", "")
            perf_rows = db.get_source_performance(source)
            if not perf_rows:
                continue

            stats = perf_rows[0]

            # Filter: minimum quality thresholds
            if stats.get("total_picks", 0) < _MIN_SAMPLE_SIZE:
                continue
            if stats.get("win_rate", 0.0) < _MIN_WIN_RATE:
                continue

            team = (signal.get("team_or_player") or "").lower()
            if team in seen_teams:
                # Deduplicate: same team already in the card
                continue
            seen_teams.add(team)

            confidence = _score_signal(signal, stats)

            scored.append(
                {
                    "signal_id": signal["id"],
                    "team_or_player": signal.get("team_or_player"),
                    "market": signal.get("market"),
                    "line": signal.get("line"),
                    "odds": signal.get("odds"),
                    "odds_decimal": signal.get("odds_decimal"),
                    "units": signal.get("units", 1.0),
                    "source": source,
                    "source_win_rate": stats.get("win_rate", 0.0),
                    "source_roi": stats.get("roi", 0.0),
                    "confidence_score": confidence,
                }
            )

        scored.sort(key=lambda s: s["confidence_score"], reverse=True)
        return scored[:max_picks]

    # ── Parlays ────────────────────────────────────────────

    def generate_parlays(
        self,
        db: Any,
        performance_engine: Any,
        max_parlays: int = 3,
    ) -> list[dict[str, Any]]:
        """Return low-variance parlay combinations from today's top picks.

        Rules:
        - Prefer 2-leg parlays
        - Allow 3-leg only for highest confidence legs
        - No same-game legs (same team in multiple legs)
        - No duplicate team exposure within one parlay
        - Minimum leg odds >= _MIN_LEG_ODDS_DECIMAL (avoids heavy chalk)
        """
        straights = self.generate_straights(db, performance_engine, max_picks=10)
        if len(straights) < 2:
            logger.debug("Not enough top picks to build parlays")
            return []

        # Filter eligible legs: must have decimal odds and meet minimum
        eligible_legs = [
            s for s in straights
            if (s.get("odds_decimal") or 0) >= _MIN_LEG_ODDS_DECIMAL
        ]

        if len(eligible_legs) < 2:
            # Fall back to all straights if filtering is too aggressive
            eligible_legs = straights[:6]

        parlays: list[dict[str, Any]] = []
        used_combinations: set[frozenset[int]] = set()

        # Generate 2-leg parlays first
        for i in range(len(eligible_legs)):
            if len(parlays) >= max_parlays:
                break
            for j in range(i + 1, len(eligible_legs)):
                leg_a = eligible_legs[i]
                leg_b = eligible_legs[j]

                combo_key = frozenset([leg_a["signal_id"], leg_b["signal_id"]])
                if combo_key in used_combinations:
                    continue

                # No same-team exposure
                teams = {
                    (leg_a.get("team_or_player") or "").lower(),
                    (leg_b.get("team_or_player") or "").lower(),
                }
                if len(teams) < 2:
                    continue

                legs = [leg_a, leg_b]
                combined = _combine_decimal_odds(legs)
                est_prob = _est_hit_probability(combined)
                combined_american = _decimal_to_american(combined)

                avg_confidence = (
                    leg_a["confidence_score"] + leg_b["confidence_score"]
                ) / 2

                parlays.append(
                    {
                        "legs": legs,
                        "num_legs": 2,
                        "combined_odds_decimal": combined,
                        "combined_odds_american": combined_american,
                        "est_hit_probability": est_prob,
                        "avg_confidence": round(avg_confidence, 4),
                        "signal_ids": [leg_a["signal_id"], leg_b["signal_id"]],
                    }
                )
                used_combinations.add(combo_key)

                if len(parlays) >= max_parlays:
                    break

        # Fill remaining slots with 3-leg parlays if we have room
        if len(parlays) < max_parlays and len(eligible_legs) >= 3:
            for i in range(len(eligible_legs)):
                if len(parlays) >= max_parlays:
                    break
                for j in range(i + 1, len(eligible_legs)):
                    for k in range(j + 1, len(eligible_legs)):
                        legs_3 = [eligible_legs[i], eligible_legs[j], eligible_legs[k]]
                        ids_3 = frozenset(l["signal_id"] for l in legs_3)
                        if ids_3 in used_combinations:
                            continue

                        teams_3 = {
                            (l.get("team_or_player") or "").lower() for l in legs_3
                        }
                        if len(teams_3) < 3:
                            continue

                        combined = _combine_decimal_odds(legs_3)
                        est_prob = _est_hit_probability(combined)
                        combined_american = _decimal_to_american(combined)
                        avg_conf = sum(l["confidence_score"] for l in legs_3) / 3

                        parlays.append(
                            {
                                "legs": legs_3,
                                "num_legs": 3,
                                "combined_odds_decimal": combined,
                                "combined_odds_american": combined_american,
                                "est_hit_probability": est_prob,
                                "avg_confidence": round(avg_conf, 4),
                                "signal_ids": [l["signal_id"] for l in legs_3],
                            }
                        )
                        used_combinations.add(ids_3)

                        if len(parlays) >= max_parlays:
                            break

        # Sort parlays by avg_confidence descending
        parlays.sort(key=lambda p: p["avg_confidence"], reverse=True)
        return parlays[:max_parlays]
