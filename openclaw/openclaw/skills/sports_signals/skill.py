"""Sports Signal Intelligence Skill.

Handles ingestion, tracking, and recommendation of sports betting signals
from multiple sources.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import ClassVar

from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill
from openclaw.skills.sports_signals.db import SignalsDB
from openclaw.skills.sports_signals.parsers import parse_message
from openclaw.skills.sports_signals.performance import PerformanceEngine
from openclaw.skills.sports_signals.recommender import RecommendationEngine

logger = logging.getLogger(__name__)

_DB_PATH = "/data/sports_signals.db"

# ── Formatting helpers ─────────────────────────────────────

_DIVIDER = "━" * 22


def _pct(val: float) -> str:
    return f"{val * 100:.1f}%"


def _odds_label(odds: str | None, dec: float | None) -> str:
    if odds:
        return odds
    if dec:
        # convert back to American roughly
        if dec >= 2.0:
            return f"+{int(round((dec - 1) * 100))}"
        else:
            return f"{int(round(-100 / (dec - 1)))}"
    return "n/a"


def _format_straights(picks: list[dict], today: str) -> str:
    if not picks:
        return f"No qualified straight bets for {today}.\n\nNeed more graded picks to rank sources."

    lines = [f"Priority Straights ({today})", _DIVIDER]
    for i, p in enumerate(picks, 1):
        team = p.get("team_or_player") or "Unknown"
        market = p.get("market") or "ML"
        odds = _odds_label(p.get("odds"), p.get("odds_decimal"))
        source = p.get("source", "?")
        wr = _pct(p.get("source_win_rate", 0))
        roi = p.get("source_roi", 0.0)
        roi_str = f"+{roi:.1f}%" if roi >= 0 else f"{roi:.1f}%"
        conf = int(p.get("confidence_score", 0) * 100)

        line_str = f" {p['line']}" if p.get("line") else ""
        lines.append(
            f"{i}. {team} {market}{line_str} ({odds}) "
            f"— {source} [{wr} win rate, {roi_str} ROI] "
            f"[{conf}% conf]"
        )

    return "\n".join(lines)


def _format_parlays(parlays: list[dict], today: str) -> str:
    if not parlays:
        return "No qualifying parlays built for today.\n\nCheck source performance or ingest more signals."

    lines = [f"Low Variance Parlays ({today})", _DIVIDER]
    for i, parlay in enumerate(parlays, 1):
        n = parlay["num_legs"]
        combined = parlay.get("combined_odds_american", "n/a")
        prob = parlay.get("est_hit_probability", 0)
        lines.append(f"Parlay {i} ({n} legs) — Combined: {combined}")
        for leg in parlay.get("legs", []):
            team = leg.get("team_or_player") or "Unknown"
            market = leg.get("market") or "ML"
            odds = _odds_label(leg.get("odds"), leg.get("odds_decimal"))
            line_str = f" {leg['line']}" if leg.get("line") else ""
            lines.append(f"  - {team} {market}{line_str} ({odds})")
        lines.append(f"  Est. probability: {_pct(prob)}")
        lines.append("")

    return "\n".join(lines).strip()


def _format_source_rankings(ranked: list[dict]) -> str:
    if not ranked:
        return "No source data yet. Ingest and grade picks first."

    lines = ["Source Performance Rankings", _DIVIDER]
    for i, s in enumerate(ranked, 1):
        source = s.get("source", "?")
        total = s.get("total_picks", 0)
        wins = s.get("wins", 0)
        losses = s.get("losses", 0)
        wr = _pct(s.get("win_rate", 0))
        roi = s.get("roi", 0.0)
        roi_str = f"+{roi:.1f}%" if roi >= 0 else f"{roi:.1f}%"
        roi_30d = s.get("roi_30d", 0.0)
        roi_30d_str = f"+{roi_30d:.1f}%" if roi_30d >= 0 else f"{roi_30d:.1f}%"
        comp = int(s.get("composite_score", 0) * 100)
        lines.append(
            f"{i}. {source}  {wins}W-{losses}L / {total} picks  "
            f"WR: {wr}  ROI: {roi_str}  ROI(30d): {roi_30d_str}  Score: {comp}"
        )

    return "\n".join(lines)


def _format_results(results: list[dict], date_str: str) -> str:
    if not results:
        return f"No graded results for {date_str}."

    wins = sum(1 for r in results if r["status"] == "win")
    losses = sum(1 for r in results if r["status"] == "loss")
    pushes = sum(1 for r in results if r["status"] == "push")

    lines = [f"Results for {date_str}  ({wins}W {losses}L {pushes}P)", _DIVIDER]
    for r in results:
        status_icon = {"win": "W", "loss": "L", "push": "P", "void": "V"}.get(r["status"], "?")
        team = r.get("team_or_player") or "?"
        market = r.get("market") or "ML"
        odds = r.get("odds") or "n/a"
        source = r.get("source", "?")
        lines.append(f"[{status_icon}] {team} {market} ({odds}) — {source}")

    return "\n".join(lines)


def _format_dashboard(db: SignalsDB, today: str) -> str:
    pending = db.get_pending_signals(limit=500)
    todays = db.get_signals_by_date(today)
    all_perf = db.get_source_performance()

    total_pending = len(pending)
    total_today = len(todays)
    num_sources = len(all_perf)

    lines = [
        "Sports Signal Intelligence — Dashboard",
        _DIVIDER,
        f"Date: {today}",
        f"Pending signals: {total_pending}",
        f"Signals today: {total_today}",
        f"Tracked sources: {num_sources}",
    ]

    if all_perf:
        lines.append("")
        lines.append("Source Summary:")
        for s in all_perf:
            wr = _pct(s.get("win_rate", 0))
            roi = s.get("roi", 0.0)
            roi_str = f"+{roi:.1f}%" if roi >= 0 else f"{roi:.1f}%"
            lines.append(f"  {s['source']}: {wr} win rate, {roi_str} ROI, {s['total_picks']} picks")

    return "\n".join(lines)


# ── The Skill ──────────────────────────────────────────────

class SportsSignalsSkill(BaseSkill):
    """Sports betting signal intelligence — ingestion, tracking, and recommendations."""

    name: ClassVar[str] = "sports_signals"
    description: ClassVar[str] = (
        "Sports betting signal intelligence — ingestion, tracking, and recommendations"
    )
    min_tier: ClassVar[int] = 1
    examples: ClassVar[list[str]] = [
        "today's straights",
        "build parlays",
        "best sources last 30 days",
        "yesterday results",
        "ingest signal",
        "grade 12 win",
        "signal dashboard",
    ]

    def __init__(self, store, inference):
        super().__init__(store, inference)
        self._db: SignalsDB | None = None
        self._perf = PerformanceEngine()
        self._rec = RecommendationEngine()

    # ── Public accessors (used by API endpoints in main.py) ──

    @property
    def db(self) -> SignalsDB:
        return self._get_db()

    @property
    def perf(self) -> PerformanceEngine:
        return self._perf

    @property
    def rec(self) -> RecommendationEngine:
        return self._rec

    def _get_db(self) -> SignalsDB:
        """Lazy-initialise SignalsDB (avoids file creation at import time)."""
        if self._db is None:
            self._db = SignalsDB(_DB_PATH)
        return self._db

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        text = ctx.message.content.strip()
        text_lower = text.lower()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        try:
            # ── Ingest ─────────────────────────────────────
            if re.search(r"\bingest\b|\bsignal\s+from\b", text_lower):
                return await self._handle_ingest(ctx, text, today)

            # ── Grade ──────────────────────────────────────
            grade_match = re.search(
                r"\bgrade\s+(\d+)\s+(win|loss|push|void)\b", text_lower
            )
            if grade_match:
                return self._handle_grade(
                    int(grade_match.group(1)), grade_match.group(2)
                )

            # ── Straights ──────────────────────────────────
            if re.search(
                r"\b(today'?s?\s*)?(straights?|picks?|daily\s+picks?)\b", text_lower
            ):
                return self._handle_straights(today)

            # ── Parlays ────────────────────────────────────
            if re.search(r"\b(build\s+)?(today'?s?\s*)?parlays?\b", text_lower):
                return self._handle_parlays(today)

            # ── Source performance ──────────────────────────
            if re.search(
                r"\b(best|top)\s+sources?\b|\bsource\s+performance\b|\bsource\s+rankings?\b",
                text_lower,
            ):
                return self._handle_source_rankings()

            # ── Results ────────────────────────────────────
            results_match = re.search(
                r"\bresults?\b.*?(\d{4}-\d{2}-\d{2})?", text_lower
            )
            if results_match or re.search(r"\byesterday'?s?\s*results?\b", text_lower):
                if "yesterday" in text_lower:
                    date_str = (
                        datetime.now(timezone.utc) - timedelta(days=1)
                    ).strftime("%Y-%m-%d")
                elif results_match and results_match.group(1):
                    date_str = results_match.group(1)
                else:
                    date_str = today
                return self._handle_results(date_str)

            # ── Dashboard / stats ──────────────────────────
            if re.search(r"\b(stats?|dashboard|overview)\b", text_lower):
                return self._handle_dashboard(today)

            # ── Default: dashboard ─────────────────────────
            return self._handle_dashboard(today)

        except Exception as exc:
            logger.exception("SportsSignalsSkill.execute failed")
            self.store.log_audit(
                ctx.message.sender_id, "sports_signals_error", str(exc), ctx.user_tier
            )
            return self._error(f"Sports signals error: {exc}")

    # ── Command handlers ───────────────────────────────────

    async def _handle_ingest(
        self, ctx: SkillContext, text: str, today: str
    ) -> SkillResponse:
        """Ingest a signal from message text."""
        db = self._get_db()

        # Determine source from text keywords or context metadata
        source = "source_b"
        if re.search(r"\bsource[_\s]?a\b", text.lower()):
            source = "source_a"
        elif re.search(r"\bsource[_\s]?b\b", text.lower()):
            source = "source_b"

        # Strip the "ingest" command word to get the actual signal text
        signal_text = re.sub(
            r"^(ingest|add\s+signal|signal\s+from\s+source[_\s]?\w+)\s*",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

        if not signal_text:
            return self._error(
                "No signal text found. Usage: ingest [source_a|source_b] <pick text>"
            )

        raw_id = db.store_raw_message(source, signal_text)
        parsed = parse_message(source, signal_text)

        if not parsed:
            return self._reply(
                f"Raw message stored (id={raw_id}) but no picks could be parsed.\n"
                f"Text: {signal_text[:200]}"
            )

        stored_ids: list[int] = []
        for sig in parsed:
            if sig.get("_raw_only"):
                continue
            sig_id = db.store_signal(
                raw_message_id=raw_id,
                source=source,
                team_or_player=sig.get("team_or_player"),
                market=sig.get("market"),
                line=sig.get("line"),
                odds=sig.get("odds"),
                odds_decimal=sig.get("odds_decimal"),
                units=sig.get("units", 1.0),
                is_parlay_leg=sig.get("is_parlay_leg", False),
                parlay_group_id=sig.get("parlay_group_id"),
            )
            stored_ids.append(sig_id)

        self.store.log_audit(
            ctx.message.sender_id,
            "sports_signals_ingest",
            f"source={source} raw_id={raw_id} signals={stored_ids}",
            ctx.user_tier,
        )

        lines = [f"Ingested {len(stored_ids)} signal(s) from {source} (raw id={raw_id}):"]
        for i, sig in enumerate(parsed):
            if sig.get("_raw_only"):
                continue
            team = sig.get("team_or_player") or "?"
            market = sig.get("market") or "ML"
            odds = sig.get("odds") or "n/a"
            lines.append(f"  {i + 1}. {team} {market} ({odds})")

        return self._reply("\n".join(lines))

    def _handle_grade(self, signal_id: int, status: str) -> SkillResponse:
        db = self._get_db()
        # Look up the signal BEFORE grading so its source is still queryable
        # regardless of whether it is still pending or already graded
        sig = db.get_signal_by_id(signal_id)
        db.grade_signal(signal_id, status)
        if sig:
            db.update_source_performance(sig["source"])
        return self._reply(f"Signal {signal_id} graded as {status.upper()}.")

    def _handle_straights(self, today: str) -> SkillResponse:
        db = self._get_db()
        picks = self._rec.generate_straights(db, self._perf)
        return self._reply(_format_straights(picks, today))

    def _handle_parlays(self, today: str) -> SkillResponse:
        db = self._get_db()
        parlays = self._rec.generate_parlays(db, self._perf)
        return self._reply(_format_parlays(parlays, today))

    def _handle_source_rankings(self) -> SkillResponse:
        db = self._get_db()
        ranked = self._perf.rank_sources(db)
        return self._reply(_format_source_rankings(ranked))

    def _handle_results(self, date_str: str) -> SkillResponse:
        db = self._get_db()
        results = db.get_results_by_date(date_str)
        return self._reply(_format_results(results, date_str))

    def _handle_dashboard(self, today: str) -> SkillResponse:
        db = self._get_db()
        return self._reply(_format_dashboard(db, today))
