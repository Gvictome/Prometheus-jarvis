"""Live Odds Skill — v0.1

Fetches and surfaces live sports odds, line movement, and best available
prices via The Odds API.

Intent keywords handled:
    live odds <sport>           — fetch and display current odds for a sport
    line movement <team>        — show line movement for a team over 24h
    best odds <event/team>      — best price across bookmakers for an event
    odds remaining              — show remaining API quota
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill
from openclaw.skills.live_odds.client import OddsClient
from openclaw.skills.live_odds.db import LiveOddsDB

logger = logging.getLogger(__name__)

_DB_PATH = "/data/live_odds.db"

# Map common sport names to API keys
_SPORT_ALIASES = {
    "nba": "basketball_nba",
    "basketball": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "football": "americanfootball_nfl",
    "ncaaf": "americanfootball_ncaaf",
    "mlb": "baseball_mlb",
    "baseball": "baseball_mlb",
    "nhl": "icehockey_nhl",
    "hockey": "icehockey_nhl",
    "mma": "mma_mixed_martial_arts",
    "ufc": "mma_mixed_martial_arts",
    "soccer": "soccer_epl",
    "epl": "soccer_epl",
    "ncaab": "basketball_ncaab",
    "college basketball": "basketball_ncaab",
    "tennis": "tennis_atp_french_open",
    "golf": "golf_masters_tournament_winner",
}


class LiveOddsSkill(BaseSkill):
    """Live sports odds skill — fetches, stores, and displays odds data.

    Commands:
        live odds <sport>         — fetch current odds
        line movement <team>      — show line movement
        best odds <team/event>    — best price across books
        odds remaining            — API quota check
    """

    name: ClassVar[str] = "live_odds"
    description: ClassVar[str] = (
        "Live sports odds — real-time lines, line movement, and best available prices"
    )
    min_tier: ClassVar[int] = 1
    examples: ClassVar[list[str]] = [
        "live odds nba",
        "live odds nfl",
        "line movement Lakers",
        "best odds Chiefs",
        "odds remaining",
    ]

    def __init__(self, store, inference):
        super().__init__(store, inference)
        self._db: LiveOddsDB | None = None
        self._client: OddsClient | None = None

    @property
    def db(self) -> LiveOddsDB:
        """Lazy-initialised database instance."""
        if self._db is None:
            self._db = LiveOddsDB(_DB_PATH)
        return self._db

    @property
    def client(self) -> OddsClient:
        """Lazy-initialised API client."""
        if self._client is None:
            self._client = OddsClient()
        return self._client

    # ── Main dispatch ─────────────────────────────────────

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        """Route live odds commands to the appropriate handler."""
        text = ctx.message.content.strip()
        text_lower = text.lower()

        try:
            # odds remaining
            if re.search(r"\bodds\s+remaining\b", text_lower):
                return self._handle_remaining()

            # line movement <team>
            movement_match = re.search(r"\bline\s+movement\s+(.+)$", text_lower)
            if movement_match:
                team = movement_match.group(1).strip()
                return self._handle_movement(team)

            # best odds <team/event>
            best_match = re.search(r"\bbest\s+odds\s+(.+)$", text_lower)
            if best_match:
                query = best_match.group(1).strip()
                return self._handle_best_odds(query)

            # live odds <sport>
            odds_match = re.search(r"\blive\s+odds\s+(.+)$", text_lower)
            if odds_match:
                sport_query = odds_match.group(1).strip()
                return await self._handle_live_odds(ctx, sport_query)

            # Generic odds trigger — show available sports
            return await self._handle_sports_list()

        except Exception as exc:
            logger.exception("LiveOddsSkill.execute failed")
            self.store.log_audit(
                ctx.message.sender_id,
                "live_odds_error",
                str(exc),
                ctx.user_tier,
            )
            return self._error(f"Live odds error: {exc}")

    # ── Command handlers ──────────────────────────────────

    async def _handle_live_odds(self, ctx: SkillContext, sport_query: str) -> SkillResponse:
        """Fetch and display current odds for a sport."""
        if not self.client.is_available:
            return self._error(
                "Live odds unavailable — ODDS_API_KEY not configured.\n"
                "Get a free key at https://the-odds-api.com/"
            )

        sport_key = _SPORT_ALIASES.get(sport_query.lower(), sport_query.lower().replace(" ", "_"))

        try:
            events_odds = await self.client.get_odds(
                sport=sport_key,
                regions="us",
                markets="h2h,spreads",
                odds_format="american",
            )
        except Exception as exc:
            return self._error(f"Failed to fetch odds for '{sport_query}': {exc}")

        if not events_odds:
            return self._reply(
                f"Live Odds — {sport_query.upper()}\n"
                "━" * 22 + "\n"
                "No live odds available right now.\n"
                "Games may not be scheduled or the sport key may be wrong."
            )

        # Store snapshots
        for event in events_odds[:20]:  # limit storage
            event_id = event.get("id", "")
            if not event_id:
                continue

            self.db.store_event(
                event_id=event_id,
                sport_key=event.get("sport_key", sport_key),
                sport_title=event.get("sport_title"),
                home_team=event.get("home_team", ""),
                away_team=event.get("away_team", ""),
                commence_time=event.get("commence_time"),
            )

            for bookmaker in event.get("bookmakers", []):
                bk_key = bookmaker.get("key", "")
                for market in bookmaker.get("markets", []):
                    market_key = market.get("key", "")
                    for outcome in market.get("outcomes", []):
                        self.db.store_snapshot(
                            event_id=event_id,
                            bookmaker=bk_key,
                            market=market_key,
                            outcome_name=outcome.get("name", ""),
                            price=outcome.get("price"),
                            point=outcome.get("point"),
                        )

        self.store.log_audit(
            ctx.message.sender_id,
            "live_odds_fetch",
            f"sport={sport_key} events={len(events_odds)}",
            ctx.user_tier,
        )

        return self._reply(self._format_odds_list(events_odds[:10], sport_query))

    def _handle_movement(self, team: str) -> SkillResponse:
        """Show line movement for a team over the last 24 hours."""
        snapshots = self.db.get_movement(team=team, market="spreads", hours=24, limit=100)
        if not snapshots:
            # Try h2h
            snapshots = self.db.get_movement(team=team, market="h2h", hours=24, limit=100)

        if not snapshots:
            return self._reply(
                f"Line Movement — {team}\n"
                "━" * 22 + "\n"
                f"No line movement data found for '{team}' in the last 24h.\n"
                "Fetch odds first with 'live odds <sport>'."
            )

        return self._reply(self._format_movement(team, snapshots))

    def _handle_best_odds(self, query: str) -> SkillResponse:
        """Show best available price across bookmakers for a team/event."""
        # Try to find matching events in DB
        all_events = self.db.get_upcoming_events(limit=200)
        matched = [
            e for e in all_events
            if query.lower() in e.get("home_team", "").lower()
            or query.lower() in e.get("away_team", "").lower()
        ]

        if not matched:
            return self._reply(
                f"Best Odds — {query}\n"
                "━" * 22 + "\n"
                f"No upcoming events found matching '{query}'.\n"
                "Fetch odds first with 'live odds <sport>'."
            )

        event = matched[0]
        best = self.db.get_best_odds(event_id=event["id"], market="h2h")
        if not best:
            best = self.db.get_best_odds(event_id=event["id"], market="spreads")

        return self._reply(self._format_best_odds(event, best))

    async def _handle_sports_list(self) -> SkillResponse:
        """Return list of active sports."""
        if not self.client.is_available:
            lines = [
                "Live Odds",
                "━" * 22,
                "Commands:",
                "  live odds nba         — NBA odds",
                "  live odds nfl         — NFL odds",
                "  live odds mlb         — MLB odds",
                "  line movement <team>  — line movement tracker",
                "  best odds <team>      — best price across books",
                "  odds remaining        — API quota status",
                "",
                "Note: ODDS_API_KEY not configured. Get a free key at https://the-odds-api.com/",
            ]
        else:
            try:
                sports = await self.client.get_sports()
                active = [s for s in sports if s.get("active")][:10]
                lines = [
                    "Live Odds — Active Sports",
                    "━" * 22,
                ]
                for s in active:
                    lines.append(f"  {s.get('title', '?')}  [{s.get('key', '?')}]")
                lines.append("")
                lines.append("Use 'live odds <sport>' to fetch lines.")
            except Exception as exc:
                lines = [f"Failed to fetch sports list: {exc}"]

        return self._reply("\n".join(lines))

    def _handle_remaining(self) -> SkillResponse:
        """Report remaining API request quota."""
        remaining = self.client.requests_remaining
        if remaining is None:
            return self._reply(
                "Odds API Quota\n"
                "━" * 22 + "\n"
                "No requests made yet this session.\n"
                "Use 'live odds <sport>' to fetch and check quota."
            )
        status = "OK" if remaining >= _WARN_THRESHOLD else "LOW"
        return self._reply(
            f"Odds API Quota — {status}\n"
            "━" * 22 + "\n"
            f"Requests remaining: {remaining}\n"
            "Free tier: 500/month. Upgrade at https://the-odds-api.com/"
        )

    # ── Formatters ────────────────────────────────────────

    def _format_odds_list(self, events: list[dict], sport: str) -> str:
        """Format a list of events with their odds."""
        lines = [f"Live Odds — {sport.upper()} ({len(events)} games)", "━" * 22]

        for event in events[:8]:
            home = event.get("home_team", "?")
            away = event.get("away_team", "?")
            commence = event.get("commence_time", "")[:10]

            lines.append(f"{away} @ {home}  [{commence}]")

            # Show first bookmaker's spread and ML
            bookmakers = event.get("bookmakers", [])
            if bookmakers:
                bk = bookmakers[0]
                for market in bk.get("markets", []):
                    mkey = market.get("key", "")
                    if mkey == "spreads":
                        outcomes = market.get("outcomes", [])
                        for o in outcomes[:2]:
                            pt = o.get("point", "")
                            pt_str = f" {'+' if pt and pt > 0 else ''}{pt}" if pt is not None else ""
                            lines.append(f"  {o.get('name','')} {pt_str} ({o.get('price','')})")
                        break
                else:
                    for market in bk.get("markets", []):
                        if market.get("key") == "h2h":
                            outcomes = market.get("outcomes", [])
                            for o in outcomes[:2]:
                                lines.append(f"  {o.get('name','')} ML {o.get('price','')}")
                            break
            lines.append("")

        remaining = self.client.requests_remaining
        if remaining is not None:
            lines.append(f"API quota: {remaining} requests remaining")

        return "\n".join(lines).strip()

    def _format_movement(self, team: str, snapshots: list[dict]) -> str:
        """Format line movement data for a team."""
        lines = [f"Line Movement — {team}", "━" * 22]

        # Group by bookmaker
        by_book: dict[str, list[dict]] = {}
        for s in snapshots:
            bk = s.get("bookmaker", "?")
            if bk not in by_book:
                by_book[bk] = []
            by_book[bk].append(s)

        for bookmaker, snaps in list(by_book.items())[:4]:
            if len(snaps) < 2:
                continue
            first = snaps[0]
            last = snaps[-1]
            first_price = first.get("price", "?")
            last_price = last.get("price", "?")
            first_point = first.get("point", "")
            last_point = last.get("point", "")

            point_str = ""
            if first_point is not None and last_point is not None and first_point != last_point:
                point_str = f" (line: {first_point} -> {last_point})"

            lines.append(f"{bookmaker.upper()}: {first_price} -> {last_price}{point_str}")

        if not lines[2:]:
            lines.append("Not enough data points to show movement (need 2+ snapshots).")

        lines.append("")
        lines.append(f"Based on {len(snapshots)} snapshots in last 24h.")
        return "\n".join(lines)

    def _format_best_odds(self, event: dict, best: list[dict]) -> str:
        """Format best available odds comparison."""
        home = event.get("home_team", "?")
        away = event.get("away_team", "?")
        lines = [
            f"Best Odds — {away} @ {home}",
            "━" * 22,
        ]

        if not best:
            lines.append("No odds data available for this event.")
            return "\n".join(lines)

        # Group by outcome
        by_outcome: dict[str, list[dict]] = {}
        for b in best:
            name = b.get("outcome_name", "?")
            if name not in by_outcome:
                by_outcome[name] = []
            by_outcome[name].append(b)

        for outcome_name, rows in by_outcome.items():
            # Sort by price descending (best odds = highest number for + lines, lowest for - lines)
            rows_sorted = sorted(rows, key=lambda x: x.get("price", 0) or 0, reverse=True)
            best_row = rows_sorted[0]
            lines.append(f"{outcome_name}: {best_row.get('price', '?')} @ {best_row.get('bookmaker', '?').upper()}")
            # Show all books for comparison
            for r in rows_sorted[1:4]:
                lines.append(f"  also: {r.get('price', '?')} @ {r.get('bookmaker', '?').upper()}")

        return "\n".join(lines)


# Module-level constant referenced in _handle_remaining
_WARN_THRESHOLD = 50
