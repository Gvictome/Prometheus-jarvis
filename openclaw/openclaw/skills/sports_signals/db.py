"""Sports Signals Intelligence — SQLite database layer.

Maintains a dedicated database at /data/sports_signals.db (separate from
the main MemoryStore) so the signals system can be deployed and backed up
independently.
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
CREATE TABLE IF NOT EXISTS raw_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    raw_text        TEXT NOT NULL,
    telegram_msg_id TEXT,
    attachments     TEXT DEFAULT '[]',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS signals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_message_id   INTEGER REFERENCES raw_messages(id),
    source           TEXT NOT NULL,
    team_or_player   TEXT,
    market           TEXT,
    line             TEXT,
    odds             TEXT,
    odds_decimal     REAL,
    units            REAL DEFAULT 1.0,
    is_parlay_leg    INTEGER DEFAULT 0,
    parlay_group_id  INTEGER,
    status           TEXT DEFAULT 'pending',
    event_id         TEXT,
    event_time       TEXT,
    graded_at        TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_signals_source  ON signals(source);
CREATE INDEX IF NOT EXISTS idx_signals_status  ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);

CREATE TABLE IF NOT EXISTS source_performance (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,
    total_picks  INTEGER DEFAULT 0,
    wins         INTEGER DEFAULT 0,
    losses       INTEGER DEFAULT 0,
    pushes       INTEGER DEFAULT 0,
    roi          REAL DEFAULT 0.0,
    roi_30d      REAL DEFAULT 0.0,
    win_rate     REAL DEFAULT 0.0,
    last_updated TEXT DEFAULT (datetime('now')),
    UNIQUE(source)
);

CREATE TABLE IF NOT EXISTS recommendations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    rec_type         TEXT NOT NULL,
    signal_ids       TEXT NOT NULL,
    combined_odds    REAL,
    est_probability  REAL,
    confidence_score REAL,
    delivered        INTEGER DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _row_to_dict(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    """Convert a sqlite3 row to a dict using cursor description."""
    return {col[0]: val for col, val in zip(cursor.description, row)}


class SignalsDB:
    """Wrapper around the sports signals SQLite database."""

    def __init__(self, db_path: str = "/data/sports_signals.db") -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_DDL)
        self._conn.commit()
        logger.info("SignalsDB initialised at %s", db_path)

    # ── Raw message ingestion ──────────────────────────────

    def store_raw_message(
        self,
        source: str,
        raw_text: str,
        telegram_msg_id: str | None = None,
        attachments: list[str] | None = None,
    ) -> int:
        """Insert a raw message and return its ID."""
        attachments_json = json.dumps(attachments or [])
        cur = self._conn.execute(
            """
            INSERT INTO raw_messages (source, raw_text, telegram_msg_id, attachments)
            VALUES (?, ?, ?, ?)
            """,
            (source, raw_text, telegram_msg_id, attachments_json),
        )
        self._conn.commit()
        row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.debug("Stored raw_message id=%d source=%s", row_id, source)
        return row_id

    # ── Signal CRUD ───────────────────────────────────────

    def store_signal(
        self,
        raw_message_id: int,
        source: str,
        team_or_player: str | None,
        market: str | None,
        line: str | None,
        odds: str | None,
        odds_decimal: float | None,
        units: float = 1.0,
        is_parlay_leg: bool = False,
        parlay_group_id: int | None = None,
    ) -> int:
        """Insert a parsed signal and return its ID."""
        cur = self._conn.execute(
            """
            INSERT INTO signals
                (raw_message_id, source, team_or_player, market, line, odds,
                 odds_decimal, units, is_parlay_leg, parlay_group_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw_message_id,
                source,
                team_or_player,
                market,
                line,
                odds,
                odds_decimal,
                units,
                1 if is_parlay_leg else 0,
                parlay_group_id,
            ),
        )
        self._conn.commit()
        row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.debug("Stored signal id=%d source=%s market=%s", row_id, source, market)
        return row_id

    def get_pending_signals(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return pending (ungraded) signals, newest first."""
        cur = self._conn.execute(
            "SELECT * FROM signals WHERE status = 'pending' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_signals_by_date(self, date_str: str) -> list[dict[str, Any]]:
        """Return all signals created on a given date (YYYY-MM-DD)."""
        cur = self._conn.execute(
            "SELECT * FROM signals WHERE date(created_at) = ? ORDER BY created_at ASC",
            (date_str,),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_signal_by_id(self, signal_id: int) -> dict[str, Any] | None:
        """Return a single signal by its ID, regardless of status."""
        cur = self._conn.execute(
            "SELECT * FROM signals WHERE id = ?",
            (signal_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def grade_signal(self, signal_id: int, status: str) -> None:
        """Update a signal's status ('win', 'loss', 'push', 'void')."""
        graded_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._conn.execute(
            "UPDATE signals SET status = ?, graded_at = ? WHERE id = ?",
            (status.lower(), graded_at, signal_id),
        )
        self._conn.commit()
        logger.info("Graded signal id=%d -> %s", signal_id, status)

    # ── Performance tracking ───────────────────────────────

    def update_source_performance(self, source: str) -> dict[str, Any]:
        """Recalculate and persist performance stats for a source.

        Returns the updated stats dict.
        """
        cur = self._conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE status IN ('win','loss','push','void')) AS total_picks,
                COUNT(*) FILTER (WHERE status = 'win')  AS wins,
                COUNT(*) FILTER (WHERE status = 'loss') AS losses,
                COUNT(*) FILTER (WHERE status = 'push') AS pushes
            FROM signals
            WHERE source = ?
            """,
            (source,),
        )
        row = dict(cur.fetchone())  # type: ignore[arg-type]

        total_picks: int = row["total_picks"] or 0
        wins: int = row["wins"] or 0
        losses: int = row["losses"] or 0

        win_rate = (wins / total_picks) if total_picks > 0 else 0.0

        # All-time ROI — assumes 1 unit per pick, -110 standard odds when no odds stored
        roi = self._calculate_roi(source, days=None)
        roi_30d = self._calculate_roi(source, days=30)

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._conn.execute(
            """
            INSERT INTO source_performance
                (source, total_picks, wins, losses, pushes, roi, roi_30d, win_rate, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                total_picks  = excluded.total_picks,
                wins         = excluded.wins,
                losses       = excluded.losses,
                pushes       = excluded.pushes,
                roi          = excluded.roi,
                roi_30d      = excluded.roi_30d,
                win_rate     = excluded.win_rate,
                last_updated = excluded.last_updated
            """,
            (source, total_picks, wins, losses, row["pushes"] or 0, roi, roi_30d, win_rate, now_str),
        )
        self._conn.commit()

        return {
            "source": source,
            "total_picks": total_picks,
            "wins": wins,
            "losses": losses,
            "pushes": row["pushes"] or 0,
            "roi": roi,
            "roi_30d": roi_30d,
            "win_rate": win_rate,
            "last_updated": now_str,
        }

    def _calculate_roi(self, source: str, days: int | None) -> float:
        """Calculate ROI for a source over the last N days (or all time if None)."""
        where = "source = ? AND status IN ('win', 'loss', 'push')"
        params: list[Any] = [source]
        if days is not None:
            where += f" AND created_at >= datetime('now', '-{days} days')"

        cur = self._conn.execute(
            f"""
            SELECT status, odds_decimal, units
            FROM signals
            WHERE {where}
            """,
            params,
        )
        rows = cur.fetchall()

        if not rows:
            return 0.0

        total_wagered = 0.0
        total_profit = 0.0

        for r in rows:
            status = r["status"]
            dec_odds = r["odds_decimal"] or 1.909  # default ~-110 in decimal
            units = r["units"] or 1.0
            total_wagered += units

            if status == "win":
                total_profit += (dec_odds - 1) * units
            elif status == "loss":
                total_profit -= units
            # push = 0 profit

        if total_wagered == 0:
            return 0.0

        return round((total_profit / total_wagered) * 100, 2)

    def get_source_performance(self, source: str | None = None) -> list[dict[str, Any]]:
        """Return performance rows for one or all sources.

        If source is None, returns all rows ordered by win_rate DESC.
        """
        if source is not None:
            cur = self._conn.execute(
                "SELECT * FROM source_performance WHERE source = ?", (source,)
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM source_performance ORDER BY win_rate DESC"
            )
        return [dict(r) for r in cur.fetchall()]

    # ── Recommendations ────────────────────────────────────

    def store_recommendation(
        self,
        rec_type: str,
        signal_ids: list[int],
        combined_odds: float | None,
        est_probability: float | None,
        confidence_score: float | None,
    ) -> int:
        """Persist a generated recommendation and return its ID."""
        cur = self._conn.execute(
            """
            INSERT INTO recommendations
                (rec_type, signal_ids, combined_odds, est_probability, confidence_score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                rec_type,
                json.dumps(signal_ids),
                combined_odds,
                est_probability,
                confidence_score,
            ),
        )
        self._conn.commit()
        row_id: int = cur.lastrowid  # type: ignore[assignment]
        return row_id

    def get_todays_recommendations(self) -> list[dict[str, Any]]:
        """Return all recommendations created today."""
        cur = self._conn.execute(
            "SELECT * FROM recommendations WHERE date(created_at) = date('now') ORDER BY confidence_score DESC"
        )
        rows = cur.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["signal_ids"] = json.loads(d.get("signal_ids", "[]"))
            results.append(d)
        return results

    def get_results_by_date(self, date_str: str) -> list[dict[str, Any]]:
        """Return graded signals for a specific date."""
        cur = self._conn.execute(
            """
            SELECT * FROM signals
            WHERE date(created_at) = ?
              AND status IN ('win', 'loss', 'push', 'void')
            ORDER BY graded_at ASC
            """,
            (date_str,),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_all_sources(self) -> list[str]:
        """Return distinct source names that have signals."""
        cur = self._conn.execute("SELECT DISTINCT source FROM signals")
        return [r[0] for r in cur.fetchall()]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
