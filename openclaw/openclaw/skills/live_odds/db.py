"""Live Odds — SQLite database layer.

Maintains a dedicated database at /data/live_odds.db for storing odds
snapshots and event data to support line movement tracking.

Schema:
    odds_snapshots  — point-in-time odds captures per bookmaker per market
    events          — sport events with status and scores
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,       -- The Odds API event_id
    sport_key       TEXT NOT NULL,
    sport_title     TEXT,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    commence_time   TEXT,                   -- ISO datetime
    completed       INTEGER DEFAULT 0,
    home_score      REAL,
    away_score      REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_sport     ON events(sport_key);
CREATE INDEX IF NOT EXISTS idx_events_commence  ON events(commence_time);
CREATE INDEX IF NOT EXISTS idx_events_completed ON events(completed);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL REFERENCES events(id),
    bookmaker       TEXT NOT NULL,
    market          TEXT NOT NULL,          -- 'h2h', 'spreads', 'totals'
    outcome_name    TEXT NOT NULL,
    price           REAL,                   -- american odds
    point           REAL,                   -- spread/total line
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_snapshots_event     ON odds_snapshots(event_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_bookmaker ON odds_snapshots(bookmaker);
CREATE INDEX IF NOT EXISTS idx_snapshots_market    ON odds_snapshots(market);
CREATE INDEX IF NOT EXISTS idx_snapshots_outcome   ON odds_snapshots(outcome_name);
CREATE INDEX IF NOT EXISTS idx_snapshots_fetched   ON odds_snapshots(fetched_at);
"""


class LiveOddsDB:
    """Wrapper around the live odds SQLite database.

    Follows the same pattern as SignalsDB and CouncilDB:
    - Single persistent connection with WAL mode
    - row_factory = sqlite3.Row for dict-compatible access
    - Foreign keys enforced
    - All DDL applied at init time
    """

    def __init__(self, db_path: str = "/data/live_odds.db") -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_DDL)
        self._conn.commit()
        logger.info("LiveOddsDB initialised at %s", db_path)

    # ── Events CRUD ───────────────────────────────────────

    def store_event(
        self,
        event_id: str,
        sport_key: str,
        sport_title: str | None,
        home_team: str,
        away_team: str,
        commence_time: str | None = None,
    ) -> None:
        """Insert or update an event record."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._conn.execute(
            """
            INSERT INTO events (id, sport_key, sport_title, home_team, away_team, commence_time, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                sport_title   = excluded.sport_title,
                home_team     = excluded.home_team,
                away_team     = excluded.away_team,
                commence_time = excluded.commence_time,
                updated_at    = excluded.updated_at
            """,
            (event_id, sport_key, sport_title, home_team, away_team, commence_time, now),
        )
        self._conn.commit()

    def update_scores(
        self,
        event_id: str,
        home_score: float | None,
        away_score: float | None,
        completed: bool = False,
    ) -> None:
        """Update scores and completion status for an event."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._conn.execute(
            """
            UPDATE events
            SET home_score = ?, away_score = ?, completed = ?, updated_at = ?
            WHERE id = ?
            """,
            (home_score, away_score, 1 if completed else 0, now, event_id),
        )
        self._conn.commit()

    def get_upcoming_events(
        self,
        sport_key: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return upcoming (not completed) events, optionally filtered by sport."""
        if sport_key:
            cur = self._conn.execute(
                """SELECT * FROM events WHERE completed = 0 AND sport_key = ?
                   ORDER BY commence_time ASC LIMIT ?""",
                (sport_key, limit),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE completed = 0 ORDER BY commence_time ASC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in cur.fetchall()]

    # ── Odds snapshots CRUD ───────────────────────────────

    def store_snapshot(
        self,
        event_id: str,
        bookmaker: str,
        market: str,
        outcome_name: str,
        price: float | None,
        point: float | None = None,
    ) -> int:
        """Insert an odds snapshot. Returns the row ID."""
        cur = self._conn.execute(
            """
            INSERT INTO odds_snapshots (event_id, bookmaker, market, outcome_name, price, point)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, bookmaker, market, outcome_name, price, point),
        )
        self._conn.commit()
        row_id: int = cur.lastrowid  # type: ignore[assignment]
        return row_id

    def get_movement(
        self,
        team: str,
        market: str = "spreads",
        hours: int = 24,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return odds snapshots for a team showing line movement over time.

        Args:
            team: Team name substring to match (case-insensitive).
            market: Market type: 'h2h', 'spreads', or 'totals'.
            hours: How many hours back to look.
            limit: Max rows to return.

        Returns:
            List of snapshots ordered by fetched_at ascending (oldest first).
        """
        cur = self._conn.execute(
            f"""
            SELECT s.*, e.home_team, e.away_team, e.sport_key, e.commence_time
            FROM odds_snapshots s
            JOIN events e ON e.id = s.event_id
            WHERE s.market = ?
              AND s.outcome_name LIKE ?
              AND s.fetched_at >= datetime('now', '-{hours} hours')
            ORDER BY s.fetched_at ASC
            LIMIT ?
            """,
            (market, f"%{team}%", limit),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_best_odds(
        self,
        event_id: str,
        market: str = "h2h",
    ) -> list[dict[str, Any]]:
        """Return the best (highest) price per outcome across all bookmakers.

        Looks at only the most recent snapshot per bookmaker/outcome combination.

        Args:
            event_id: Event ID to look up.
            market: Market type: 'h2h', 'spreads', or 'totals'.

        Returns:
            List of dicts with outcome_name, bookmaker, price, point.
        """
        cur = self._conn.execute(
            """
            SELECT outcome_name, bookmaker, price, point, MAX(fetched_at) AS latest_at
            FROM odds_snapshots
            WHERE event_id = ? AND market = ?
            GROUP BY outcome_name, bookmaker
            ORDER BY outcome_name, price DESC
            """,
            (event_id, market),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_latest_odds_for_sport(
        self,
        sport_key: str,
        market: str = "h2h",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return the most recent odds snapshot per event for a sport.

        Args:
            sport_key: Sport key, e.g. 'basketball_nba'.
            market: Market type.
            limit: Max events to return.

        Returns:
            List of event+odds dicts.
        """
        cur = self._conn.execute(
            """
            SELECT s.event_id, s.outcome_name, s.bookmaker, s.price, s.point,
                   s.fetched_at, e.home_team, e.away_team, e.commence_time
            FROM odds_snapshots s
            JOIN events e ON e.id = s.event_id
            WHERE e.sport_key = ? AND s.market = ?
              AND s.fetched_at = (
                  SELECT MAX(s2.fetched_at)
                  FROM odds_snapshots s2
                  WHERE s2.event_id = s.event_id
                    AND s2.bookmaker = s.bookmaker
                    AND s2.market = s.market
                    AND s2.outcome_name = s.outcome_name
              )
            ORDER BY e.commence_time ASC
            LIMIT ?
            """,
            (sport_key, market, limit),
        )
        return [dict(r) for r in cur.fetchall()]

    # ── Close ─────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
