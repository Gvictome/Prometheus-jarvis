"""Sports Signals — message parsers.

Parser B  (primary)  — structured text picks like:
    Tage Thompson 0.5 goals (+115)
    Sabres ML
    Stars ML
    Lightning ML
    (3 leg parlay +450)

Parser A  (secondary) — sportsbook share link messages:
    Stores the raw text + extracts any URLs.
"""

from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── American odds → decimal conversion ────────────────────

def american_to_decimal(american: str) -> float | None:
    """Convert American odds string like '+115' or '-110' to decimal odds."""
    try:
        val = int(american.replace(" ", ""))
    except (ValueError, AttributeError):
        return None

    if val > 0:
        return round(1 + val / 100, 4)
    elif val < 0:
        return round(1 - 100 / val, 4)
    return None


# ── Regex building blocks ──────────────────────────────────

# American odds: +115, -110, + 115, (−110)
_RE_ODDS = re.compile(r"[(\s]?([+\-]\s?\d{2,4})[)\s]?")
_RE_ODDS_STANDALONE = re.compile(r"\(([+\-]\d{2,4})\)")

# Units: "2u", "2 units", "1.5u"
_RE_UNITS = re.compile(r"(\d+(?:\.\d+)?)\s*u(?:nits?)?", re.IGNORECASE)

# Over/under lines: o6.5, u6.5, over 6.5, under 6.5
_RE_TOTAL_LINE = re.compile(r"\b([ou]/?ver?|under)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

# Spread: -3.5, +3.5 (when not immediately following +/- sign attached to odds context)
_RE_SPREAD_LINE = re.compile(r"\b([+\-]\d+(?:\.\d+)?)\b")

# Parlay marker line
_RE_PARLAY_LINE = re.compile(
    r"\(?\s*(\d+)\s*[\-\s]?leg\s+parlay\b|\bparlay\b.*?([+\-]\d{2,4})?",
    re.IGNORECASE,
)

# URL extractor
_RE_URL = re.compile(r"https?://[^\s\)\"']+")

# Known ML keywords
_ML_KEYWORDS = {"ml", "moneyline", "money line", "to win"}

# Known total keywords
_TOTAL_KEYWORDS = {"over", "under", "o/u", "o6", "u6", "goals", "pts", "points", "runs", "total"}

# Known prop stat keywords (non-exhaustive — extend as needed)
_PROP_STAT_KEYWORDS = {
    "goals", "assists", "shots", "points", "rebounds", "assists", "strikeouts",
    "hits", "yards", "touchdowns", "saves", "blocks", "steals", "turnovers",
    "receptions", "carries", "completions"
}


def _detect_market(token_text: str) -> tuple[str, str | None]:
    """Heuristically detect market type.

    Returns (market, line) where market is 'ML'|'spread'|'total'|'prop'.
    """
    t = token_text.lower().strip()

    # Moneyline
    for kw in _ML_KEYWORDS:
        if kw in t:
            return "ML", None

    # Total (over/under) — look for numeric line
    total_match = _RE_TOTAL_LINE.search(t)
    if total_match or any(kw in t for kw in {"over", "under", "o/u"}):
        line = total_match.group(2) if total_match else None
        direction = total_match.group(1)[0].upper() if total_match else None
        line_str = f"{direction}/{line}" if direction and line else line
        return "total", line_str

    # Prop — player name + stat keyword
    for kw in _PROP_STAT_KEYWORDS:
        if kw in t:
            # Extract the numeric line near the stat keyword
            spread_m = _RE_SPREAD_LINE.search(t)
            line_str = spread_m.group(1) if spread_m else None
            return "prop", line_str

    # Spread — look for explicit +/- number in context
    spread_m = _RE_SPREAD_LINE.search(t)
    if spread_m:
        return "spread", spread_m.group(1)

    # Default to ML when no other market detected
    return "ML", None


def _strip_odds_from_text(text: str) -> str:
    """Remove parenthesised odds from a text snippet so we can parse the pick."""
    return _RE_ODDS_STANDALONE.sub("", text).strip()


# ── Parser B — structured text picks ──────────────────────

class ParserB:
    """Primary parser for structured text pick messages."""

    def parse(self, raw_text: str) -> list[dict[str, Any]]:
        """Parse a raw message into a list of signal dicts.

        Each signal dict has keys matching the `signals` table (minus IDs/timestamps).
        """
        lines = [ln.strip() for ln in raw_text.strip().splitlines() if ln.strip()]
        if not lines:
            return []

        signals: list[dict[str, Any]] = []
        parlay_group_id: int | None = None
        is_parlay_block = False

        # First pass: detect if this is a parlay message
        for line in lines:
            if _RE_PARLAY_LINE.search(line):
                is_parlay_block = True
                # Use a simple counter as parlay group ID (seconds since epoch would be heavier)
                import time
                parlay_group_id = int(time.time())
                break

        for line in lines:
            # Skip parlay summary lines (they're metadata, not picks)
            if _RE_PARLAY_LINE.search(line) and not self._looks_like_pick(line):
                logger.debug("Skipping parlay summary line: %s", line)
                continue

            sig = self._parse_pick_line(line, is_parlay_block, parlay_group_id)
            if sig:
                signals.append(sig)

        return signals

    def _looks_like_pick(self, line: str) -> bool:
        """Return True if the line contains a team/player name (not just a parlay summary)."""
        # A pick line normally has words that aren't just numbers and parlay keywords
        cleaned = _RE_PARLAY_LINE.sub("", line).strip()
        cleaned = _RE_ODDS_STANDALONE.sub("", cleaned).strip()
        return bool(re.search(r"[a-zA-Z]{3,}", cleaned))

    def _parse_pick_line(
        self,
        line: str,
        is_parlay_leg: bool,
        parlay_group_id: int | None,
    ) -> dict[str, Any] | None:
        """Parse a single pick line into a signal dict."""
        # Extract parenthesised odds first
        odds_match = _RE_ODDS_STANDALONE.search(line)
        odds_str: str | None = None
        odds_decimal: float | None = None
        if odds_match:
            odds_str = odds_match.group(1)
            odds_decimal = american_to_decimal(odds_str)

        # Strip odds from the line for cleaner market/player detection
        clean_line = _strip_odds_from_text(line)

        # Extract units
        units = 1.0
        units_match = _RE_UNITS.search(clean_line)
        if units_match:
            try:
                units = float(units_match.group(1))
            except ValueError:
                pass
            clean_line = _RE_UNITS.sub("", clean_line).strip()

        # Market detection from the cleaned line
        market, line_val = _detect_market(clean_line)

        # Team/player is what remains after removing market keyword tokens
        team_or_player = self._extract_team_or_player(clean_line, market)

        if not team_or_player:
            logger.debug("Could not extract team/player from: %s", line)
            return None

        return {
            "team_or_player": team_or_player,
            "market": market,
            "line": line_val,
            "odds": odds_str,
            "odds_decimal": odds_decimal,
            "units": units,
            "is_parlay_leg": is_parlay_leg,
            "parlay_group_id": parlay_group_id,
        }

    def _extract_team_or_player(self, clean_line: str, market: str) -> str | None:
        """Extract the team or player name from a cleaned pick line."""
        # Remove known market suffixes
        remove_patterns = [
            r"\bml\b", r"\bmoneyline\b", r"\bmoney\s+line\b",
            r"\bover\b", r"\bunder\b", r"\bo/u\b",
            r"\bspread\b",
            r"[+\-]\d+(?:\.\d+)?",   # spread/line numbers
            r"\d+(?:\.\d+)?\s*u\b",  # units
        ]
        result = clean_line
        for pat in remove_patterns:
            result = re.sub(pat, "", result, flags=re.IGNORECASE)

        # Also strip prop stat keywords that were part of the market detection
        for kw in _PROP_STAT_KEYWORDS:
            result = re.sub(rf"\b{re.escape(kw)}\b", "", result, flags=re.IGNORECASE)

        result = re.sub(r"\s+", " ", result).strip(" ,-.()")
        return result if len(result) >= 2 else None


# ── Parser A — share link / attachment messages ────────────

class ParserA:
    """Secondary parser for sportsbook share link messages.

    Does minimal text parsing — mainly stores raw content and extracts URLs.
    Attempts basic pick parsing as a best-effort.
    """

    def __init__(self) -> None:
        self._parser_b = ParserB()

    def parse(self, raw_text: str) -> list[dict[str, Any]]:
        """Parse a share-link message.

        Returns signal dicts. URLs are captured in a separate 'urls' key
        (not stored in signals table directly but available for logging).
        """
        urls = _RE_URL.findall(raw_text)
        logger.debug("Parser A found %d URLs in message", len(urls))

        # Strip URLs from text and attempt best-effort text parse
        text_without_urls = _RE_URL.sub("", raw_text).strip()
        signals = self._parser_b.parse(text_without_urls) if text_without_urls else []

        # Annotate with URL context
        for sig in signals:
            sig["_source_urls"] = urls

        # If no signals were parsed but we have URLs, return a stub entry
        if not signals and urls:
            signals.append({
                "team_or_player": None,
                "market": None,
                "line": None,
                "odds": None,
                "odds_decimal": None,
                "units": 1.0,
                "is_parlay_leg": False,
                "parlay_group_id": None,
                "_source_urls": urls,
                "_raw_only": True,
            })

        return signals


# ── Public dispatch ────────────────────────────────────────

def parse_message(
    source: str,
    raw_text: str,
) -> list[dict[str, Any]]:
    """Route a raw message to the appropriate parser and return signal dicts.

    source: 'source_a' (share links) or 'source_b' (text picks)
    """
    if source == "source_a":
        return ParserA().parse(raw_text)
    else:
        # Default to parser B for unknown sources too
        return ParserB().parse(raw_text)
