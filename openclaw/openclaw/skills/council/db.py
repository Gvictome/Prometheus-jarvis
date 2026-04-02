"""Council of AI Agents — SQLite database layer.

Maintains a dedicated database at /data/council.db for storing debate
history and per-agent opinions.

Schema:
    debates         — council debate sessions with final verdicts
    agent_opinions  — individual agent opinions per debate
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
CREATE TABLE IF NOT EXISTS debates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic           TEXT NOT NULL,
    context         TEXT,               -- JSON context passed to agents
    consensus       TEXT NOT NULL,      -- 'strong_buy', 'buy', 'neutral', 'sell', 'strong_sell'
    confidence      REAL DEFAULT 0.0,
    summary         TEXT,               -- moderator synthesis text
    bull_score      REAL DEFAULT 0.0,
    bear_score      REAL DEFAULT 0.0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_debates_created ON debates(created_at);
CREATE INDEX IF NOT EXISTS idx_debates_consensus ON debates(consensus);

CREATE TABLE IF NOT EXISTS agent_opinions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id   INTEGER NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    agent_name  TEXT NOT NULL,
    stance      TEXT NOT NULL,
    confidence  REAL DEFAULT 0.5,
    reasoning   TEXT,
    key_factors TEXT DEFAULT '[]',  -- JSON list
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_opinions_debate   ON agent_opinions(debate_id);
CREATE INDEX IF NOT EXISTS idx_opinions_agent    ON agent_opinions(agent_name);
"""


class CouncilDB:
    """Wrapper around the council SQLite database.

    Follows the same pattern as SignalsDB and PoliticianDB:
    - Single persistent connection with WAL mode
    - row_factory = sqlite3.Row for dict-compatible access
    - Foreign keys enforced
    - All DDL applied at init time
    """

    def __init__(self, db_path: str = "/data/council.db") -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_DDL)
        self._conn.commit()
        logger.info("CouncilDB initialised at %s", db_path)

    # ── Debate CRUD ───────────────────────────────────────

    def store_debate(
        self,
        topic: str,
        consensus: str,
        confidence: float,
        summary: str,
        bull_score: float,
        bear_score: float,
        context: dict[str, Any] | None = None,
    ) -> int:
        """Store a completed council debate. Returns the debate ID."""
        cur = self._conn.execute(
            """
            INSERT INTO debates (topic, context, consensus, confidence, summary, bull_score, bear_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                topic,
                json.dumps(context or {}),
                consensus,
                confidence,
                summary,
                bull_score,
                bear_score,
            ),
        )
        self._conn.commit()
        debate_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.info("Stored debate id=%d topic=%r consensus=%s", debate_id, topic[:60], consensus)
        return debate_id

    def store_opinions(
        self,
        debate_id: int,
        opinions: list[dict[str, Any]],
    ) -> None:
        """Store all agent opinions for a debate."""
        for op in opinions:
            self._conn.execute(
                """
                INSERT INTO agent_opinions (debate_id, agent_name, stance, confidence, reasoning, key_factors)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    debate_id,
                    op.get("agent_name", ""),
                    op.get("stance", "neutral"),
                    op.get("confidence", 0.5),
                    op.get("reasoning", ""),
                    json.dumps(op.get("key_factors", [])),
                ),
            )
        self._conn.commit()
        logger.debug("Stored %d opinions for debate_id=%d", len(opinions), debate_id)

    def get_debate(self, debate_id: int) -> dict[str, Any] | None:
        """Return a single debate by ID with all agent opinions."""
        row = self._conn.execute(
            "SELECT * FROM debates WHERE id = ?", (debate_id,)
        ).fetchone()
        if not row:
            return None
        debate = dict(row)
        debate["context"] = json.loads(debate.get("context") or "{}")
        debate["opinions"] = self.get_debate_opinions(debate_id)
        return debate

    def get_debate_opinions(self, debate_id: int) -> list[dict[str, Any]]:
        """Return all agent opinions for a debate."""
        cur = self._conn.execute(
            "SELECT * FROM agent_opinions WHERE debate_id = ? ORDER BY id",
            (debate_id,),
        )
        results = []
        for row in cur.fetchall():
            d = dict(row)
            d["key_factors"] = json.loads(d.get("key_factors") or "[]")
            results.append(d)
        return results

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the N most recent debates, newest first."""
        cur = self._conn.execute(
            """
            SELECT id, topic, consensus, confidence, summary, bull_score, bear_score, created_at
            FROM debates
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    # ── Close ─────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
