"""Politician Intelligence — SQLite database layer.

Maintains a dedicated database at /data/politician_intel.db (separate from
the main MemoryStore and sports_signals.db) so the politician system can be
deployed and backed up independently.

Schema: 9 tables
    politicians         — tracked congressional members
    stock_trades        — STOCK Act filings (Senate eFD + House disclosures)
    votes               — roll-call votes with relevance scoring
    bills               — bills introduced/co-sponsored with relevance scoring
    campaign_finance    — FEC + OpenSecrets donation data
    lobbying_contacts   — Senate LDA lobbying registrations
    statements          — press releases and floor remarks + sentiment
    intel_alerts        — generated intelligence alerts
    scrape_cache        — HTTP response cache to avoid hammering rate-limited APIs
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS politicians (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bioguide_id     TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    party           TEXT,
    state           TEXT,
    chamber         TEXT,           -- 'senate' or 'house'
    district        TEXT,           -- House district or NULL for Senate
    committees      TEXT DEFAULT '[]',  -- JSON list of committee names
    tracked         INTEGER DEFAULT 1,  -- 1 = actively monitored
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_politicians_bioguide ON politicians(bioguide_id);
CREATE INDEX IF NOT EXISTS idx_politicians_chamber  ON politicians(chamber);
CREATE INDEX IF NOT EXISTS idx_politicians_tracked  ON politicians(tracked);

CREATE TABLE IF NOT EXISTS stock_trades (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    politician_id       INTEGER NOT NULL REFERENCES politicians(id),
    ticker              TEXT NOT NULL,
    company_name        TEXT,
    transaction_type    TEXT NOT NULL,  -- 'purchase', 'sale', 'sale_full', 'exchange'
    amount_range        TEXT,           -- e.g. '$1,001 - $15,000'
    amount_min          REAL,           -- parsed lower bound for analysis
    amount_max          REAL,           -- parsed upper bound for analysis
    filed_date          TEXT,           -- date the disclosure was filed
    traded_date         TEXT,           -- date the actual trade occurred
    source              TEXT,           -- 'senate_efd' or 'house_disclosures'
    pdf_url             TEXT,           -- link to original filing PDF
    raw_text            TEXT,           -- extracted PDF text
    is_gaming_stock     INTEGER DEFAULT 0,  -- 1 if ticker in GAMING_TICKERS
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_trades_politician  ON stock_trades(politician_id);
CREATE INDEX IF NOT EXISTS idx_trades_ticker      ON stock_trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_filed       ON stock_trades(filed_date);
CREATE INDEX IF NOT EXISTS idx_trades_gaming      ON stock_trades(is_gaming_stock);

CREATE TABLE IF NOT EXISTS votes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    politician_id   INTEGER NOT NULL REFERENCES politicians(id),
    bill_id         INTEGER REFERENCES bills(id),
    congress_vote_id TEXT,            -- e.g. 'h2024-123'
    vote_cast       TEXT NOT NULL,    -- 'Yea', 'Nay', 'Not Voting', 'Present'
    category        TEXT,             -- 'gambling', 'sports', 'stadium', 'finance', 'other'
    relevance_score REAL DEFAULT 0.0, -- 0.0-1.0
    voted_at        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_votes_politician ON votes(politician_id);
CREATE INDEX IF NOT EXISTS idx_votes_bill       ON votes(bill_id);
CREATE INDEX IF NOT EXISTS idx_votes_relevance  ON votes(relevance_score);

CREATE TABLE IF NOT EXISTS bills (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    congress_bill_id TEXT NOT NULL UNIQUE, -- e.g. 'hr-118-4567'
    title            TEXT NOT NULL,
    summary          TEXT,
    status           TEXT,             -- 'introduced', 'passed_house', 'passed_senate', 'enacted', 'failed'
    category         TEXT,             -- 'gambling', 'sports', 'stadium', 'tribal_gaming', 'other'
    relevance_score  REAL DEFAULT 0.0,
    sponsor_id       INTEGER REFERENCES politicians(id),
    congress_number  INTEGER,
    bill_type        TEXT,             -- 'hr', 's', 'hjres', 'sjres'
    bill_number      TEXT,
    introduced_at    TEXT,
    last_action_at   TEXT,
    source_url       TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bills_congress_id  ON bills(congress_bill_id);
CREATE INDEX IF NOT EXISTS idx_bills_category     ON bills(category);
CREATE INDEX IF NOT EXISTS idx_bills_relevance    ON bills(relevance_score);
CREATE INDEX IF NOT EXISTS idx_bills_status       ON bills(status);

CREATE VIRTUAL TABLE IF NOT EXISTS bills_fts USING fts5(
    title, summary, category,
    content='bills',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS bills_fts_insert AFTER INSERT ON bills BEGIN
    INSERT INTO bills_fts(rowid, title, summary, category)
    VALUES (new.id, new.title, new.summary, new.category);
END;

CREATE TRIGGER IF NOT EXISTS bills_fts_update AFTER UPDATE ON bills BEGIN
    INSERT INTO bills_fts(bills_fts, rowid, title, summary, category)
    VALUES ('delete', old.id, old.title, old.summary, old.category);
    INSERT INTO bills_fts(rowid, title, summary, category)
    VALUES (new.id, new.title, new.summary, new.category);
END;

CREATE TABLE IF NOT EXISTS campaign_finance (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    politician_id  INTEGER NOT NULL REFERENCES politicians(id),
    cycle          INTEGER NOT NULL,   -- election cycle year e.g. 2024
    industry       TEXT NOT NULL,      -- e.g. 'gambling', 'entertainment', 'real_estate'
    pac_name       TEXT,
    total_received REAL DEFAULT 0.0,
    num_donations  INTEGER DEFAULT 0,
    source         TEXT,               -- 'opensecrets' or 'fec'
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(politician_id, cycle, industry, pac_name)
);

CREATE INDEX IF NOT EXISTS idx_finance_politician ON campaign_finance(politician_id);
CREATE INDEX IF NOT EXISTS idx_finance_industry   ON campaign_finance(industry);
CREATE INDEX IF NOT EXISTS idx_finance_cycle      ON campaign_finance(cycle);

CREATE TABLE IF NOT EXISTS lobbying_contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    politician_id   INTEGER NOT NULL REFERENCES politicians(id),
    lobbyist_firm   TEXT NOT NULL,
    client          TEXT NOT NULL,   -- who hired the lobbyist
    issue_area      TEXT,            -- 'gambling', 'sports', 'gaming', etc.
    amount          REAL,            -- reported lobbying spend
    filing_year     INTEGER,
    filing_period   TEXT,            -- 'Q1', 'Q2', 'Q3', 'Q4', 'mid-year', 'year-end'
    lda_filing_id   TEXT,            -- Senate LDA unique filing ID
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_lobbying_politician ON lobbying_contacts(politician_id);
CREATE INDEX IF NOT EXISTS idx_lobbying_client     ON lobbying_contacts(client);
CREATE INDEX IF NOT EXISTS idx_lobbying_year       ON lobbying_contacts(filing_year);

CREATE TABLE IF NOT EXISTS statements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    politician_id   INTEGER NOT NULL REFERENCES politicians(id),
    source          TEXT NOT NULL,   -- 'propublica', 'twitter', 'press_release', 'floor_remarks'
    source_url      TEXT,
    content         TEXT NOT NULL,
    sentiment_score REAL,            -- -1.0 (negative) to +1.0 (positive) via VADER
    relevance_score REAL DEFAULT 0.0,
    category        TEXT,
    published_at    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_statements_politician  ON statements(politician_id);
CREATE INDEX IF NOT EXISTS idx_statements_sentiment   ON statements(sentiment_score);
CREATE INDEX IF NOT EXISTS idx_statements_relevance   ON statements(relevance_score);

CREATE VIRTUAL TABLE IF NOT EXISTS statements_fts USING fts5(
    content, category,
    content='statements',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS statements_fts_insert AFTER INSERT ON statements BEGIN
    INSERT INTO statements_fts(rowid, content, category)
    VALUES (new.id, new.content, new.category);
END;

CREATE TABLE IF NOT EXISTS intel_alerts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    politician_id    INTEGER NOT NULL REFERENCES politicians(id),
    alert_type       TEXT NOT NULL,     -- 'gaming_trade', 'bill_vote', 'state_bill', 'finance', 'lobbying'
    severity         TEXT NOT NULL,     -- 'critical', 'high', 'medium', 'low'
    sports_relevance REAL DEFAULT 0.0,  -- 0.0-1.0 composite score
    ticker           TEXT,              -- primary affected gaming ticker if applicable
    tickers_affected TEXT DEFAULT '[]', -- JSON list of all affected tickers
    title            TEXT NOT NULL,
    detail           TEXT,
    source_table     TEXT,              -- which table triggered this alert
    source_id        INTEGER,           -- ID in source_table
    delivered        INTEGER DEFAULT 0, -- 1 once pushed to Telegram/WhatsApp
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_alerts_politician   ON intel_alerts(politician_id);
CREATE INDEX IF NOT EXISTS idx_alerts_severity     ON intel_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_ticker       ON intel_alerts(ticker);
CREATE INDEX IF NOT EXISTS idx_alerts_delivered    ON intel_alerts(delivered);
CREATE INDEX IF NOT EXISTS idx_alerts_created      ON intel_alerts(created_at);

CREATE TABLE IF NOT EXISTS scrape_cache (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash     TEXT NOT NULL UNIQUE,  -- SHA256 of normalised URL
    url          TEXT NOT NULL,
    content_hash TEXT,                  -- SHA256 of response body (change detection)
    body         TEXT,                  -- cached response body
    status_code  INTEGER,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at   TEXT                   -- NULL = never expire manually
);

CREATE INDEX IF NOT EXISTS idx_cache_url_hash  ON scrape_cache(url_hash);
CREATE INDEX IF NOT EXISTS idx_cache_expires   ON scrape_cache(expires_at);
"""


def _row_to_dict(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    """Convert a sqlite3 row to a dict using cursor description."""
    return {col[0]: val for col, val in zip(cursor.description, row)}


class PoliticianDB:
    """Wrapper around the politician intelligence SQLite database.

    Follows the same pattern as SignalsDB in sports_signals/db.py:
    - Single persistent connection with WAL mode
    - row_factory = sqlite3.Row for dict-compatible access
    - Foreign keys enforced
    - All DDL applied at init time
    """

    def __init__(self, db_path: str = "/data/politician_intel.db") -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_DDL)
        self._conn.commit()
        logger.info("PoliticianDB initialised at %s", db_path)

    # ── Politician CRUD ────────────────────────────────────

    def upsert_politician(
        self,
        bioguide_id: str,
        name: str,
        party: str | None = None,
        state: str | None = None,
        chamber: str | None = None,
        district: str | None = None,
        committees: list[str] | None = None,
        tracked: bool = True,
    ) -> int:
        """Insert or update a politician record. Returns the row ID."""
        committees_json = json.dumps(committees or [])
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur = self._conn.execute(
            """
            INSERT INTO politicians
                (bioguide_id, name, party, state, chamber, district, committees, tracked, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bioguide_id) DO UPDATE SET
                name       = excluded.name,
                party      = excluded.party,
                state      = excluded.state,
                chamber    = excluded.chamber,
                district   = excluded.district,
                committees = excluded.committees,
                tracked    = excluded.tracked,
                updated_at = excluded.updated_at
            """,
            (bioguide_id, name, party, state, chamber, district, committees_json,
             1 if tracked else 0, now),
        )
        self._conn.commit()
        # Fetch id after upsert
        row = self._conn.execute(
            "SELECT id FROM politicians WHERE bioguide_id = ?", (bioguide_id,)
        ).fetchone()
        row_id: int = row["id"]
        logger.debug("Upserted politician bioguide_id=%s id=%d", bioguide_id, row_id)
        return row_id

    def get_politician(self, bioguide_id: str) -> dict[str, Any] | None:
        """Return a politician record by bioguide_id, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM politicians WHERE bioguide_id = ?", (bioguide_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["committees"] = json.loads(d.get("committees") or "[]")
        return d

    def get_tracked_politicians(self) -> list[dict[str, Any]]:
        """Return all politicians where tracked=1, ordered by chamber then name."""
        cur = self._conn.execute(
            "SELECT * FROM politicians WHERE tracked = 1 ORDER BY chamber, name"
        )
        results = []
        for row in cur.fetchall():
            d = dict(row)
            d["committees"] = json.loads(d.get("committees") or "[]")
            results.append(d)
        return results

    def search_politicians(self, query: str) -> list[dict[str, Any]]:
        """Search politicians by name (LIKE match, case-insensitive)."""
        cur = self._conn.execute(
            "SELECT * FROM politicians WHERE name LIKE ? ORDER BY name",
            (f"%{query}%",),
        )
        results = []
        for row in cur.fetchall():
            d = dict(row)
            d["committees"] = json.loads(d.get("committees") or "[]")
            results.append(d)
        return results

    # ── Stock trades CRUD ─────────────────────────────────

    def store_trade(
        self,
        politician_id: int,
        ticker: str,
        transaction_type: str,
        amount_range: str | None = None,
        amount_min: float | None = None,
        amount_max: float | None = None,
        filed_date: str | None = None,
        traded_date: str | None = None,
        source: str = "senate_efd",
        pdf_url: str | None = None,
        raw_text: str | None = None,
        company_name: str | None = None,
        is_gaming_stock: bool = False,
    ) -> int:
        """Insert a stock trade filing. Returns the row ID."""
        cur = self._conn.execute(
            """
            INSERT INTO stock_trades
                (politician_id, ticker, company_name, transaction_type, amount_range,
                 amount_min, amount_max, filed_date, traded_date, source, pdf_url,
                 raw_text, is_gaming_stock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                politician_id, ticker, company_name, transaction_type, amount_range,
                amount_min, amount_max, filed_date, traded_date, source, pdf_url,
                raw_text, 1 if is_gaming_stock else 0,
            ),
        )
        self._conn.commit()
        row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.debug("Stored trade id=%d politician_id=%d ticker=%s", row_id, politician_id, ticker)
        return row_id

    def get_gaming_trades(
        self,
        days: int = 90,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return gaming stock trades filed in the last N days, newest first."""
        cur = self._conn.execute(
            """
            SELECT t.*, p.name AS politician_name, p.party, p.state, p.chamber
            FROM stock_trades t
            JOIN politicians p ON p.id = t.politician_id
            WHERE t.is_gaming_stock = 1
              AND t.filed_date >= date('now', ?)
            ORDER BY t.filed_date DESC
            LIMIT ?
            """,
            (f"-{days} days", limit),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_trades_by_politician(
        self,
        politician_id: int,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return all trades for a specific politician, newest first."""
        cur = self._conn.execute(
            "SELECT * FROM stock_trades WHERE politician_id = ? ORDER BY filed_date DESC LIMIT ?",
            (politician_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]

    # ── Bills CRUD ────────────────────────────────────────

    def upsert_bill(
        self,
        congress_bill_id: str,
        title: str,
        summary: str | None = None,
        status: str | None = None,
        category: str | None = None,
        relevance_score: float = 0.0,
        sponsor_id: int | None = None,
        congress_number: int | None = None,
        bill_type: str | None = None,
        bill_number: str | None = None,
        introduced_at: str | None = None,
        last_action_at: str | None = None,
        source_url: str | None = None,
    ) -> int:
        """Insert or update a bill record. Returns the row ID."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur = self._conn.execute(
            """
            INSERT INTO bills
                (congress_bill_id, title, summary, status, category, relevance_score,
                 sponsor_id, congress_number, bill_type, bill_number,
                 introduced_at, last_action_at, source_url, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(congress_bill_id) DO UPDATE SET
                title           = excluded.title,
                summary         = excluded.summary,
                status          = excluded.status,
                category        = excluded.category,
                relevance_score = excluded.relevance_score,
                last_action_at  = excluded.last_action_at,
                updated_at      = excluded.updated_at
            """,
            (
                congress_bill_id, title, summary, status, category, relevance_score,
                sponsor_id, congress_number, bill_type, bill_number,
                introduced_at, last_action_at, source_url, now,
            ),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id FROM bills WHERE congress_bill_id = ?", (congress_bill_id,)
        ).fetchone()
        return int(row["id"])

    def get_relevant_bills(
        self,
        min_score: float = 0.3,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return bills above a relevance threshold, optionally filtered by category."""
        if category:
            cur = self._conn.execute(
                """SELECT * FROM bills WHERE relevance_score >= ? AND category = ?
                   ORDER BY relevance_score DESC, introduced_at DESC LIMIT ?""",
                (min_score, category, limit),
            )
        else:
            cur = self._conn.execute(
                """SELECT * FROM bills WHERE relevance_score >= ?
                   ORDER BY relevance_score DESC, introduced_at DESC LIMIT ?""",
                (min_score, limit),
            )
        return [dict(r) for r in cur.fetchall()]

    def search_bills_fts(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Full-text search across bill titles and summaries using FTS5."""
        cur = self._conn.execute(
            """
            SELECT b.* FROM bills b
            JOIN bills_fts f ON f.rowid = b.id
            WHERE bills_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        )
        return [dict(r) for r in cur.fetchall()]

    # ── Votes CRUD ────────────────────────────────────────

    def store_vote(
        self,
        politician_id: int,
        vote_cast: str,
        bill_id: int | None = None,
        congress_vote_id: str | None = None,
        category: str | None = None,
        relevance_score: float = 0.0,
        voted_at: str | None = None,
    ) -> int:
        """Insert a vote record. Returns the row ID."""
        cur = self._conn.execute(
            """
            INSERT INTO votes
                (politician_id, bill_id, congress_vote_id, vote_cast,
                 category, relevance_score, voted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (politician_id, bill_id, congress_vote_id, vote_cast,
             category, relevance_score, voted_at),
        )
        self._conn.commit()
        row_id: int = cur.lastrowid  # type: ignore[assignment]
        return row_id

    # ── Campaign finance CRUD ─────────────────────────────

    def upsert_finance(
        self,
        politician_id: int,
        cycle: int,
        industry: str,
        total_received: float,
        pac_name: str | None = None,
        num_donations: int = 0,
        source: str = "opensecrets",
    ) -> None:
        """Insert or update a campaign finance record."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._conn.execute(
            """
            INSERT INTO campaign_finance
                (politician_id, cycle, industry, total_received, pac_name, num_donations, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(politician_id, cycle, industry, pac_name) DO UPDATE SET
                total_received = excluded.total_received,
                num_donations  = excluded.num_donations,
                updated_at     = excluded.updated_at
            """,
            (politician_id, cycle, industry, total_received, pac_name, num_donations, source, now),
        )
        self._conn.commit()

    def get_gaming_finance(
        self,
        cycle: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return campaign finance rows for gambling/gaming industry donors."""
        where = "industry IN ('gambling', 'gaming', 'casinos', 'sports_betting')"
        params: list[Any] = []
        if cycle:
            where += " AND cycle = ?"
            params.append(cycle)
        cur = self._conn.execute(
            f"""
            SELECT f.*, p.name AS politician_name, p.party, p.state, p.chamber
            FROM campaign_finance f
            JOIN politicians p ON p.id = f.politician_id
            WHERE {where}
            ORDER BY total_received DESC
            LIMIT ?
            """,
            params + [limit],
        )
        return [dict(r) for r in cur.fetchall()]

    # ── Lobbying CRUD ─────────────────────────────────────

    def store_lobbying(
        self,
        politician_id: int,
        lobbyist_firm: str,
        client: str,
        issue_area: str | None = None,
        amount: float | None = None,
        filing_year: int | None = None,
        filing_period: str | None = None,
        lda_filing_id: str | None = None,
    ) -> int:
        """Insert a lobbying contact record. Returns the row ID."""
        cur = self._conn.execute(
            """
            INSERT INTO lobbying_contacts
                (politician_id, lobbyist_firm, client, issue_area, amount,
                 filing_year, filing_period, lda_filing_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (politician_id, lobbyist_firm, client, issue_area, amount,
             filing_year, filing_period, lda_filing_id),
        )
        self._conn.commit()
        row_id: int = cur.lastrowid  # type: ignore[assignment]
        return row_id

    # ── Statements CRUD ───────────────────────────────────

    def store_statement(
        self,
        politician_id: int,
        source: str,
        content: str,
        source_url: str | None = None,
        sentiment_score: float | None = None,
        relevance_score: float = 0.0,
        category: str | None = None,
        published_at: str | None = None,
    ) -> int:
        """Insert a statement record. Returns the row ID."""
        cur = self._conn.execute(
            """
            INSERT INTO statements
                (politician_id, source, source_url, content, sentiment_score,
                 relevance_score, category, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (politician_id, source, source_url, content, sentiment_score,
             relevance_score, category, published_at),
        )
        self._conn.commit()
        row_id: int = cur.lastrowid  # type: ignore[assignment]
        return row_id

    def search_statements_fts(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Full-text search across statement content using FTS5."""
        cur = self._conn.execute(
            """
            SELECT s.* FROM statements s
            JOIN statements_fts f ON f.rowid = s.id
            WHERE statements_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        )
        return [dict(r) for r in cur.fetchall()]

    # ── Intel alerts CRUD ─────────────────────────────────

    def store_alert(
        self,
        politician_id: int,
        alert_type: str,
        severity: str,
        title: str,
        sports_relevance: float = 0.0,
        ticker: str | None = None,
        tickers_affected: list[str] | None = None,
        detail: str | None = None,
        source_table: str | None = None,
        source_id: int | None = None,
    ) -> int:
        """Insert an intel alert. Returns the row ID."""
        cur = self._conn.execute(
            """
            INSERT INTO intel_alerts
                (politician_id, alert_type, severity, sports_relevance,
                 ticker, tickers_affected, title, detail, source_table, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                politician_id, alert_type, severity, sports_relevance,
                ticker, json.dumps(tickers_affected or []),
                title, detail, source_table, source_id,
            ),
        )
        self._conn.commit()
        row_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.info(
            "Stored alert id=%d type=%s severity=%s ticker=%s",
            row_id, alert_type, severity, ticker,
        )
        return row_id

    def get_undelivered_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return alerts not yet delivered, ordered by severity and creation time."""
        severity_order = "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"
        cur = self._conn.execute(
            f"""
            SELECT a.*, p.name AS politician_name, p.party, p.state
            FROM intel_alerts a
            JOIN politicians p ON p.id = a.politician_id
            WHERE a.delivered = 0
            ORDER BY {severity_order} ASC, a.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        results = []
        for row in cur.fetchall():
            d = dict(row)
            d["tickers_affected"] = json.loads(d.get("tickers_affected") or "[]")
            results.append(d)
        return results

    def mark_alert_delivered(self, alert_id: int) -> None:
        """Mark an alert as delivered."""
        self._conn.execute(
            "UPDATE intel_alerts SET delivered = 1 WHERE id = ?", (alert_id,)
        )
        self._conn.commit()

    def get_recent_alerts(
        self,
        days: int = 7,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return alerts from the last N days, optionally filtered by severity."""
        where = f"a.created_at >= datetime('now', '-{days} days')"
        params: list[Any] = []
        if severity:
            where += " AND a.severity = ?"
            params.append(severity)
        cur = self._conn.execute(
            f"""
            SELECT a.*, p.name AS politician_name, p.party, p.state
            FROM intel_alerts a
            JOIN politicians p ON p.id = a.politician_id
            WHERE {where}
            ORDER BY a.created_at DESC
            LIMIT ?
            """,
            params + [limit],
        )
        results = []
        for row in cur.fetchall():
            d = dict(row)
            d["tickers_affected"] = json.loads(d.get("tickers_affected") or "[]")
            results.append(d)
        return results

    # ── Scrape cache ──────────────────────────────────────

    def cache_get(self, url: str) -> dict[str, Any] | None:
        """Return a cached HTTP response for a URL, or None if not found/expired."""
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        row = self._conn.execute(
            """
            SELECT * FROM scrape_cache
            WHERE url_hash = ?
              AND (expires_at IS NULL OR expires_at > datetime('now'))
            """,
            (url_hash,),
        ).fetchone()
        return dict(row) if row else None

    def cache_set(
        self,
        url: str,
        body: str,
        status_code: int = 200,
        expires_at: str | None = None,
    ) -> None:
        """Store or replace a cached HTTP response."""
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        content_hash = hashlib.sha256(body.encode()).hexdigest()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._conn.execute(
            """
            INSERT INTO scrape_cache (url_hash, url, content_hash, body, status_code, fetched_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url_hash) DO UPDATE SET
                content_hash = excluded.content_hash,
                body         = excluded.body,
                status_code  = excluded.status_code,
                fetched_at   = excluded.fetched_at,
                expires_at   = excluded.expires_at
            """,
            (url_hash, url, content_hash, body, status_code, now, expires_at),
        )
        self._conn.commit()

    def cache_changed(self, url: str, new_body: str) -> bool:
        """Return True if the content hash for this URL has changed."""
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        row = self._conn.execute(
            "SELECT content_hash FROM scrape_cache WHERE url_hash = ?", (url_hash,)
        ).fetchone()
        if not row:
            return True
        return row["content_hash"] != hashlib.sha256(new_body.encode()).hexdigest()

    # ── Close ─────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
