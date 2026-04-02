"""Sports betting market link engine — actual data, not stubs.

Maps political events (trades, bills, votes) to their expected impact on
sports betting markets, specific gaming tickers, and bet market dynamics.

This module contains the full reference data mappings used by the signal
engine. No NotImplementedError stubs here — these are the authoritative
lookup tables for the politician intel system.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Gaming ticker universe ─────────────────────────────────

GAMING_TICKERS: dict[str, dict[str, Any]] = {
    "DKNG": {
        "company":      "DraftKings Inc.",
        "category":     "online_sportsbook",
        "primary_states": ["MA", "NY", "NJ", "PA", "IL", "CO", "IN", "VA", "TN", "AZ"],
        "market_cap_tier": "large",  # >$10B
        "sensitivity":  "very_high",  # most sensitive to federal/state legislation
        "notes":        "Pure-play online betting; every new state legalization is directly additive.",
    },
    "PENN": {
        "company":      "PENN Entertainment Inc.",
        "category":     "casino_online_hybrid",
        "primary_states": ["PA", "OH", "IL", "IN", "MS", "MO", "IA", "CO", "WV"],
        "market_cap_tier": "large",
        "sensitivity":  "high",
        "notes":        "ESPN Bet partnership. Brick-and-mortar + online. Regional casino footprint matters.",
    },
    "MGM": {
        "company":      "MGM Resorts International",
        "category":     "casino_online_hybrid",
        "primary_states": ["NV", "NJ", "MD", "MS", "OH", "MI"],
        "market_cap_tier": "large",
        "sensitivity":  "medium",
        "notes":        "BetMGM joint venture with Entain. Diverse revenue base (hotels, entertainment).",
    },
    "CZR": {
        "company":      "Caesars Entertainment Inc.",
        "category":     "casino_online_hybrid",
        "primary_states": ["NV", "NJ", "PA", "IL", "IN", "LA", "MS"],
        "market_cap_tier": "large",
        "sensitivity":  "medium",
        "notes":        "Caesars Sportsbook. High debt load makes regulatory risk more impactful on stock.",
    },
    "FLUT": {
        "company":      "Flutter Entertainment plc",
        "category":     "online_sportsbook",
        "primary_states": ["NY", "NJ", "PA", "IL", "CO", "IN", "VA", "TN"],
        "market_cap_tier": "large",
        "sensitivity":  "very_high",
        "notes":        "FanDuel parent (US). Most liquid betting stock. Highly correlated to DKNG on legislation news.",
    },
    "CHDN": {
        "company":      "Churchill Downs Inc.",
        "category":     "horse_racing_casino",
        "primary_states": ["KY", "PA", "IL", "FL", "OH", "CO"],
        "market_cap_tier": "mid",
        "sensitivity":  "medium",
        "notes":        "Kentucky Derby + TwinSpires. Horse racing handle; less exposed to sports betting legislation.",
    },
    "WYNN": {
        "company":      "Wynn Resorts Ltd.",
        "category":     "luxury_casino",
        "primary_states": ["NV", "MA"],
        "market_cap_tier": "mid",
        "sensitivity":  "low",
        "notes":        "Primarily destination casino (Las Vegas, Macau). Limited US sports betting exposure.",
    },
    "LVS": {
        "company":      "Las Vegas Sands Corp.",
        "category":     "luxury_casino",
        "primary_states": ["NV"],
        "market_cap_tier": "large",
        "sensitivity":  "low",
        "notes":        "No US online betting. Macau/Singapore focused. Sensitive to TX casino legalization effort.",
    },
    "BYD": {
        "company":      "Boyd Gaming Corp.",
        "category":     "regional_casino",
        "primary_states": ["NV", "LA", "MS", "IN", "IA", "KS", "OH", "PA"],
        "market_cap_tier": "mid",
        "sensitivity":  "medium",
        "notes":        "Regional brick-and-mortar focus. FanDuel partner for online in some states.",
    },
    "EVRI": {
        "company":      "Everi Holdings Inc.",
        "category":     "gaming_technology",
        "primary_states": ["NV", "IL", "PA", "OH"],
        "market_cap_tier": "small",
        "sensitivity":  "medium",
        "notes":        "Gaming machines and fintech for casinos. Less direct legislative exposure.",
    },
    "BALY": {
        "company":      "Bally's Corporation",
        "category":     "casino_online_hybrid",
        "primary_states": ["RI", "IL", "CO", "NJ", "IN", "WV"],
        "market_cap_tier": "small",
        "sensitivity":  "high",
        "notes":        "Small cap; high beta to gambling legislation news. Bally's Interactive online unit.",
    },
    "GAN": {
        "company":      "GAN Limited",
        "category":     "b2b_gaming_technology",
        "primary_states": ["NJ", "PA", "MI", "WV"],
        "market_cap_tier": "small",
        "sensitivity":  "medium",
        "notes":        "B2B iGaming platform provider; benefits from any new iGaming state launches.",
    },
    "SRAD": {
        "company":      "Sportradar Group AG",
        "category":     "sports_data",
        "primary_states": [],  # data company, state-agnostic
        "market_cap_tier": "mid",
        "sensitivity":  "medium",
        "notes":        "Official data partner for NFL, NBA, NHL. Handle growth directly drives revenue.",
    },
    "RSI": {
        "company":      "Rush Street Interactive Inc.",
        "category":     "online_sportsbook",
        "primary_states": ["IL", "IN", "CO", "PA", "NJ", "MI"],
        "market_cap_tier": "small",
        "sensitivity":  "high",
        "notes":        "BetRivers.com. Small cap; high upside from new state launches.",
    },
    "GDEN": {
        "company":      "Golden Entertainment Inc.",
        "category":     "regional_casino",
        "primary_states": ["NV", "MT"],
        "market_cap_tier": "small",
        "sensitivity":  "low",
        "notes":        "Nevada tavern gaming + Montana sports betting. Limited legislative exposure.",
    },
}

# ── Bill category to market impact mapping ────────────────

BILL_CATEGORIES: dict[str, dict[str, Any]] = {
    "federal_online_gambling_ban": {
        "description":    "Federal bill to prohibit or severely restrict online gambling",
        "impact":         "bearish",
        "severity":       "critical",
        "primary_tickers": ["DKNG", "FLUT", "PENN", "CZR", "MGM", "BALY", "RSI"],
        "market_impact":  "All online betting operators severely impacted. Pure-plays (DKNG, FLUT) most exposed.",
        "betting_impact": "Major reduction in available markets; handle would collapse in affected states.",
    },
    "federal_sports_betting_framework": {
        "description":    "Federal framework to regulate (not ban) online sports betting",
        "impact":         "bullish",
        "severity":       "high",
        "primary_tickers": ["DKNG", "FLUT", "PENN", "CZR", "MGM", "SRAD"],
        "market_impact":  "Provides regulatory certainty; likely expands total addressable market.",
        "betting_impact": "Could open additional states; clarifies tax/advertising rules for operators.",
    },
    "state_online_betting_legalization": {
        "description":    "State bill to legalize mobile/online sports betting",
        "impact":         "bullish",
        "severity":       "high",
        "primary_tickers": ["DKNG", "FLUT", "PENN", "CZR", "MGM", "RSI", "BALY"],
        "market_impact":  "Directly additive — new state market opens for all licensed operators.",
        "betting_impact": "Increases total handle; new bettors + new market liquidity.",
        "state_multiplier": {
            "TX": 3.0,   # largest unlegalized market
            "CA": 2.8,   # second largest; failed 2022 prop
            "FL": 2.0,   # Seminole compact ongoing
            "NY": 0.5,   # already legal
            "NJ": 0.5,   # already legal
        },
    },
    "state_igaming_legalization": {
        "description":    "State bill to legalize online casino gaming (slots/table games)",
        "impact":         "bullish",
        "severity":       "high",
        "primary_tickers": ["DKNG", "PENN", "MGM", "CZR", "GAN", "BALY"],
        "market_impact":  "iGaming generates 3-5x the revenue of sports betting per user.",
        "betting_impact": "Separate from sports betting; only 6 states currently legal.",
    },
    "gambling_advertising_restriction": {
        "description":    "Bill to restrict gambling advertising (TV, digital, in-stadium)",
        "impact":         "bearish",
        "severity":       "medium",
        "primary_tickers": ["DKNG", "FLUT", "PENN", "CZR"],
        "market_impact":  "Raises customer acquisition costs; hits profitability for online-heavy operators.",
        "betting_impact": "Reduces new bettor acquisition; existing bettors largely unaffected.",
    },
    "gambling_tax_increase": {
        "description":    "State or federal bill to increase gaming/betting tax rates",
        "impact":         "bearish",
        "severity":       "medium",
        "primary_tickers": ["DKNG", "FLUT", "PENN", "CZR", "MGM", "BALY"],
        "market_impact":  "Directly reduces operator margins; thinner lines passed to bettors.",
        "betting_impact": "May reduce odds competitiveness in affected jurisdiction.",
    },
    "tribal_gaming_compact": {
        "description":    "State tribal gaming compact — expansion or restriction",
        "impact":         "mixed",
        "severity":       "medium",
        "primary_tickers": ["DKNG", "FLUT", "BYD", "MGM"],
        "market_impact":  "Impact depends on compact terms; tribal exclusivity = bearish for commercial operators.",
        "betting_impact": "Tribal-controlled mobile = limited handle growth for commercial books.",
    },
    "stadium_public_funding": {
        "description":    "Public funding approval for new stadium or arena",
        "impact":         "bullish",
        "severity":       "low",
        "primary_tickers": ["DKNG", "FLUT", "SRAD"],
        "market_impact":  "Anchors franchise to market; long-term handle growth in that city.",
        "betting_impact": "New/better venue = higher attendance = more in-stadium betting kiosks.",
    },
    "problem_gambling_regulation": {
        "description":    "Enhanced problem gambling requirements, self-exclusion mandates",
        "impact":         "slightly_bearish",
        "severity":       "low",
        "primary_tickers": ["DKNG", "FLUT", "PENN", "CZR"],
        "market_impact":  "Compliance costs increase; some high-value bettors may self-exclude.",
        "betting_impact": "Marginal impact on handle; high-value segment most affected.",
    },
    "wire_act_reinterpretation": {
        "description":    "DOJ or legislative action on the Wire Act (interstate gambling)",
        "impact":         "bearish",
        "severity":       "critical",
        "primary_tickers": ["DKNG", "FLUT", "PENN", "CZR", "MGM", "GAN"],
        "market_impact":  "Wire Act uncertainty is the single largest federal risk for online gambling.",
        "betting_impact": "Could invalidate multi-state poker/gaming pools and cross-state bets.",
    },
}

# ── Committee to issue jurisdiction mapping ────────────────

COMMITTEE_JURISDICTION: dict[str, list[str]] = {
    "Senate Commerce, Science, and Transportation": [
        "federal_sports_betting_framework",
        "gambling_advertising_restriction",
        "sports_data_rights",
        "stadium_public_funding",
    ],
    "Senate Judiciary": [
        "wire_act_reinterpretation",
        "federal_online_gambling_ban",
        "tribal_gaming_compact",
        "gambling_regulation",
    ],
    "Senate Finance": [
        "gambling_tax_increase",
        "gaming_excise_tax",
    ],
    "House Energy and Commerce": [
        "federal_sports_betting_framework",
        "gambling_advertising_restriction",
        "consumer_protection_gambling",
        "online_gambling_regulation",
    ],
    "House Judiciary": [
        "wire_act_reinterpretation",
        "federal_online_gambling_ban",
        "tribal_gaming_compact",
    ],
    "House Ways and Means": [
        "gambling_tax_increase",
        "gaming_excise_tax",
    ],
}

# ── State legalization priority ranking ───────────────────

STATE_MARKET_PRIORITY: dict[str, dict[str, Any]] = {
    "TX": {"population": 30_000_000, "est_annual_handle_bn": 8.0,  "status": "not_legal", "notes": "Largest prize; multiple failed attempts."},
    "CA": {"population": 39_000_000, "est_annual_handle_bn": 7.5,  "status": "not_legal", "notes": "Prop 27 failed 2022; tribal opposition."},
    "FL": {"population": 22_000_000, "est_annual_handle_bn": 4.5,  "status": "tribal_only", "notes": "Seminole compact; Hard Rock app active."},
    "GA": {"population": 11_000_000, "est_annual_handle_bn": 2.2,  "status": "not_legal", "notes": "Bills introduced multiple sessions."},
    "MN": {"population": 5_600_000,  "est_annual_handle_bn": 1.1,  "status": "not_legal", "notes": "Tribal opposition key hurdle."},
    "MO": {"population": 6_200_000,  "est_annual_handle_bn": 1.2,  "status": "retail_only", "notes": "Mobile bill repeatedly stalls in Senate."},
    "AL": {"population": 5_100_000,  "est_annual_handle_bn": 0.9,  "status": "not_legal", "notes": "Conservative state; lottery doesn't even exist."},
    "OK": {"population": 4_000_000,  "est_annual_handle_bn": 0.7,  "status": "not_legal", "notes": "Tribal gaming dominant; complicates legalization."},
    "SC": {"population": 5_200_000,  "est_annual_handle_bn": 0.9,  "status": "not_legal", "notes": "No lottery; long road."},
    "UT": {"population": 3_400_000,  "est_annual_handle_bn": 0.0,  "status": "not_legal", "notes": "Constitutional prohibition; extremely unlikely."},
}


class SportsLinkEngine:
    """Maps political events to sports betting market impact.

    Uses the GAMING_TICKERS, BILL_CATEGORIES, COMMITTEE_JURISDICTION, and
    STATE_MARKET_PRIORITY reference data to enrich intel alerts with:
        - Affected ticker list
        - Expected market direction (bullish/bearish/mixed)
        - Severity classification
        - Betting market impact description
    """

    def get_affected_tickers(
        self,
        bill_category: str,
        state: str | None = None,
    ) -> list[str]:
        """Return the list of gaming tickers most affected by a bill category.

        Args:
            bill_category: Category key from BILL_CATEGORIES.
            state: Optional state code for state-specific bills.

        Returns:
            List of ticker symbols ordered by expected impact magnitude.
        """
        cat = BILL_CATEGORIES.get(bill_category)
        if not cat:
            return []
        return list(cat.get("primary_tickers", []))

    def get_bill_impact(self, bill_category: str) -> dict[str, Any]:
        """Return full impact dict for a bill category.

        Args:
            bill_category: Category key from BILL_CATEGORIES.

        Returns:
            Impact dict with keys: impact, severity, market_impact, betting_impact.
            Returns empty dict if category not found.
        """
        return BILL_CATEGORIES.get(bill_category, {})

    def get_state_priority(self, state_code: str) -> dict[str, Any]:
        """Return market priority data for a state legalization bill.

        Args:
            state_code: Two-letter state code (e.g., 'TX', 'CA').

        Returns:
            Priority dict with est_annual_handle_bn, status, notes.
            Returns empty dict if state not in priority map.
        """
        return STATE_MARKET_PRIORITY.get(state_code.upper(), {})

    def get_committee_jurisdiction(self, committee_name: str) -> list[str]:
        """Return the list of bill categories a committee has jurisdiction over.

        Args:
            committee_name: Full committee name string.

        Returns:
            List of bill category keys this committee influences.
        """
        for committee, categories in COMMITTEE_JURISDICTION.items():
            if committee.lower() in committee_name.lower():
                return categories
        return []

    def ticker_sensitivity(self, ticker: str) -> str:
        """Return the sensitivity level for a gaming ticker.

        Args:
            ticker: Ticker symbol (e.g., 'DKNG').

        Returns:
            Sensitivity string: 'very_high', 'high', 'medium', or 'low'.
            Returns 'unknown' if ticker not in GAMING_TICKERS.
        """
        info = GAMING_TICKERS.get(ticker.upper(), {})
        return info.get("sensitivity", "unknown")

    def build_alert_context(
        self,
        event_type: str,
        politician_name: str,
        ticker: str | None = None,
        bill_category: str | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        """Build a rich alert context dict combining all relevant mapping data.

        This is the primary method called by IntelSignalEngine when constructing
        alert detail strings. Returns a dict ready to be serialised into
        intel_alerts.detail.

        Args:
            event_type: Alert type string (e.g., 'gaming_trade', 'state_bill').
            politician_name: Display name of the politician.
            ticker: Gaming ticker if a trade was involved.
            bill_category: Bill category key from BILL_CATEGORIES.
            state: State code for state-level bills.

        Returns:
            Context dict with keys: tickers_affected, impact, severity,
            market_impact, betting_impact, state_priority.
        """
        context: dict[str, Any] = {
            "event_type":      event_type,
            "politician_name": politician_name,
        }

        if ticker:
            ticker_info = GAMING_TICKERS.get(ticker.upper(), {})
            context["ticker_info"] = {
                "ticker":      ticker.upper(),
                "company":     ticker_info.get("company", ""),
                "sensitivity": ticker_info.get("sensitivity", "unknown"),
                "category":    ticker_info.get("category", ""),
            }

        if bill_category:
            impact = BILL_CATEGORIES.get(bill_category, {})
            context["tickers_affected"] = impact.get("primary_tickers", [])
            context["impact"]           = impact.get("impact", "unknown")
            context["severity"]         = impact.get("severity", "low")
            context["market_impact"]    = impact.get("market_impact", "")
            context["betting_impact"]   = impact.get("betting_impact", "")
        else:
            context["tickers_affected"] = [ticker] if ticker else []

        if state:
            context["state_priority"] = STATE_MARKET_PRIORITY.get(state.upper(), {})

        return context
