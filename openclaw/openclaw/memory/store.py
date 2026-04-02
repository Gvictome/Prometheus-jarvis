"""Memory store — SQLite (default) or PostgreSQL (when DATABASE_URL is set)."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from openclaw.config import settings

logger = logging.getLogger(__name__)

# ── SQLite schema ─────────────────────────────────────────────────────────────

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    channel     TEXT NOT NULL,
    sender_id   TEXT NOT NULL,
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    metadata    TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    channel         TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    metadata        TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content_rowid='id',
    content='messages'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    content     TEXT NOT NULL,
    category    TEXT DEFAULT 'general',
    embedding   BLOB,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    metadata    TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    content_rowid='id',
    content='memories'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TABLE IF NOT EXISTS cost_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd    REAL DEFAULT 0.0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    metadata    TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_cost_time ON cost_log(created_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    action      TEXT NOT NULL,
    detail      TEXT,
    tier        INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);

CREATE TABLE IF NOT EXISTS approvals (
    request_id      TEXT PRIMARY KEY,
    request_type    TEXT NOT NULL,
    description     TEXT NOT NULL,
    proposed_change TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at     TEXT,
    resolved_by     TEXT
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
"""

# ── PostgreSQL schema ─────────────────────────────────────────────────────────

_PG_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS conversations (
        id          TEXT PRIMARY KEY,
        channel     TEXT NOT NULL,
        sender_id   TEXT NOT NULL,
        started_at  TIMESTAMPTZ DEFAULT NOW(),
        updated_at  TIMESTAMPTZ DEFAULT NOW(),
        metadata    TEXT DEFAULT '{}'
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        id              SERIAL PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id),
        role            TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
        content         TEXT NOT NULL,
        channel         TEXT,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        metadata        TEXT DEFAULT '{}'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(created_at)",
    """CREATE TABLE IF NOT EXISTS memories (
        id          SERIAL PRIMARY KEY,
        user_id     TEXT NOT NULL,
        content     TEXT NOT NULL,
        category    TEXT DEFAULT 'general',
        embedding   BYTEA,
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        metadata    TEXT DEFAULT '{}'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)",
    """CREATE TABLE IF NOT EXISTS cost_log (
        id              SERIAL PRIMARY KEY,
        provider        TEXT NOT NULL,
        model           TEXT NOT NULL,
        input_tokens    INTEGER DEFAULT 0,
        output_tokens   INTEGER DEFAULT 0,
        cost_usd        DOUBLE PRECISION DEFAULT 0.0,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        metadata        TEXT DEFAULT '{}'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cost_time ON cost_log(created_at)",
    """CREATE TABLE IF NOT EXISTS audit_log (
        id          SERIAL PRIMARY KEY,
        user_id     TEXT NOT NULL,
        action      TEXT NOT NULL,
        detail      TEXT,
        tier        INTEGER DEFAULT 0,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)",
    """CREATE TABLE IF NOT EXISTS approvals (
        request_id      TEXT PRIMARY KEY,
        request_type    TEXT NOT NULL,
        description     TEXT NOT NULL,
        proposed_change TEXT NOT NULL DEFAULT '{}',
        status          TEXT NOT NULL DEFAULT 'pending',
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        resolved_at     TIMESTAMPTZ,
        resolved_by     TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status)",
]


# ── SQLite backend ────────────────────────────────────────────────────────────

class _SQLiteBackend:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SQLITE_SCHEMA)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_or_create_conversation(self, conversation_id: str, channel: str, sender_id: str) -> str:
        row = self.conn.execute(
            "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conversation_id,),
            )
        else:
            self.conn.execute(
                "INSERT INTO conversations (id, channel, sender_id) VALUES (?, ?, ?)",
                (conversation_id, channel, sender_id),
            )
        self.conn.commit()
        return conversation_id

    def add_message(self, conversation_id: str, role: str, content: str,
                    channel: str | None = None, metadata: dict[str, Any] | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO messages (conversation_id, role, content, channel, metadata) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, channel, json.dumps(metadata or {})),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_conversation_history(self, conversation_id: str, limit: int = 20) -> list[dict[str, str]]:
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def search_messages(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        safe_query = '"' + query.replace('"', ' ') + '"'
        rows = self.conn.execute(
            "SELECT m.id, m.conversation_id, m.role, m.content, m.created_at "
            "FROM messages_fts fts JOIN messages m ON fts.rowid = m.id "
            "WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?",
            (safe_query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_memory(self, user_id: str, content: str, category: str = "general",
                   embedding: bytes | None = None, metadata: dict[str, Any] | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO memories (user_id, content, category, embedding, metadata) VALUES (?, ?, ?, ?, ?)",
            (user_id, content, category, embedding, json.dumps(metadata or {})),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_memories(self, user_id: str, category: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        if category:
            rows = self.conn.execute(
                "SELECT id, content, category, created_at FROM memories "
                "WHERE user_id = ? AND category = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, category, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, content, category, created_at FROM memories "
                "WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_memories(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        safe_query = '"' + query.replace('"', ' ') + '"'
        rows = self.conn.execute(
            "SELECT m.id, m.user_id, m.content, m.category, m.created_at "
            "FROM memories_fts fts JOIN memories m ON fts.rowid = m.id "
            "WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
            (safe_query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_memories_with_embeddings(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, content, category, embedding FROM memories "
            "WHERE user_id = ? AND embedding IS NOT NULL ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def log_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int, cost_usd: float):
        self.conn.execute(
            "INSERT INTO cost_log (provider, model, input_tokens, output_tokens, cost_usd) VALUES (?, ?, ?, ?, ?)",
            (provider, model, input_tokens, output_tokens, cost_usd),
        )
        self.conn.commit()

    def get_monthly_cost(self) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) as total FROM cost_log "
            "WHERE created_at >= date('now', 'start of month')"
        ).fetchone()
        return row["total"]

    def log_audit(self, user_id: str, action: str, detail: str | None = None, tier: int = 0):
        self.conn.execute(
            "INSERT INTO audit_log (user_id, action, detail, tier) VALUES (?, ?, ?, ?)",
            (user_id, action, detail, tier),
        )
        self.conn.commit()

    def query_audit_log(
        self,
        where_clause: str = "",
        params: tuple = (),
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query the audit_log table with an optional WHERE clause.

        This is the safe public method for reading audit records — use it
        instead of accessing backend internals directly.
        """
        sql = "SELECT action, detail, user_id, created_at FROM audit_log"
        if where_clause:
            sql += f" WHERE {where_clause}"
        sql += f" ORDER BY created_at DESC LIMIT {limit}"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def save_approval(
        self,
        request_id: str,
        request_type: str,
        description: str,
        proposed_change: dict[str, Any],
        status: str = "pending",
        resolved_at: str | None = None,
        resolved_by: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO approvals "
            "(request_id, request_type, description, proposed_change, status, resolved_at, resolved_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (request_id, request_type, description, json.dumps(proposed_change),
             status, resolved_at, resolved_by),
        )
        self.conn.commit()

    def load_approvals(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM approvals ORDER BY created_at DESC"
            ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["proposed_change"] = json.loads(d.get("proposed_change") or "{}")
            results.append(d)
        return results


# ── PostgreSQL backend ────────────────────────────────────────────────────────

class _PostgreSQLBackend:
    """PostgreSQL backend using psycopg2 with a connection pool.

    Uses psycopg2.pool.ThreadedConnectionPool so connections are reused
    across the async event loop without leaking.  Each method checks out a
    connection, uses it, then returns it immediately.
    """

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._pool = None
        self._init_schema()
        self._pool = self._create_pool()

    def _create_pool(self):
        import psycopg2.pool
        return psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=self._database_url,
        )

    def _connect(self):
        """Check out a connection from the pool."""
        return self._pool.getconn()

    def _release(self, conn) -> None:
        """Return a connection to the pool."""
        if self._pool:
            self._pool.putconn(conn)

    def _init_schema(self):
        import psycopg2
        conn = psycopg2.connect(self._database_url)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                for stmt in _PG_SCHEMA:
                    try:
                        cur.execute(stmt)
                    except Exception as exc:
                        logger.warning("Schema statement skipped: %s", exc)
                # Add GIN trigram index for text search if not exists
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_messages_content_trgm "
                        "ON messages USING GIN (content gin_trgm_ops)"
                    )
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_memories_content_trgm "
                        "ON memories USING GIN (content gin_trgm_ops)"
                    )
                except Exception as exc:
                    logger.warning("GIN trigram index setup skipped: %s", exc)
        finally:
            conn.close()

    def close(self):
        if self._pool:
            self._pool.closeall()
            self._pool = None

    def get_or_create_conversation(self, conversation_id: str, channel: str, sender_id: str) -> str:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM conversations WHERE id = %s", (conversation_id,))
                if cur.fetchone():
                    cur.execute("UPDATE conversations SET updated_at = NOW() WHERE id = %s", (conversation_id,))
                else:
                    cur.execute(
                        "INSERT INTO conversations (id, channel, sender_id) VALUES (%s, %s, %s)",
                        (conversation_id, channel, sender_id),
                    )
            conn.commit()
        finally:
            self._release(conn)
        return conversation_id

    def add_message(self, conversation_id: str, role: str, content: str,
                    channel: str | None = None, metadata: dict[str, Any] | None = None) -> int:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO messages (conversation_id, role, content, channel, metadata) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (conversation_id, role, content, channel, json.dumps(metadata or {})),
                )
                row_id = cur.fetchone()[0]
            conn.commit()
        finally:
            self._release(conn)
        return row_id

    def get_conversation_history(self, conversation_id: str, limit: int = 20) -> list[dict[str, str]]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT role, content FROM messages WHERE conversation_id = %s "
                    "ORDER BY created_at DESC LIMIT %s",
                    (conversation_id, limit),
                )
                rows = cur.fetchall()
        finally:
            self._release(conn)
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def search_messages(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                # Use GIN trigram similarity search if available, fall back to ILIKE
                cur.execute(
                    "SELECT id, conversation_id, role, content, created_at FROM messages "
                    "WHERE content ILIKE %s ORDER BY created_at DESC LIMIT %s",
                    (f"%{query}%", limit),
                )
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
        finally:
            self._release(conn)
        return [dict(zip(cols, r)) for r in rows]

    def add_memory(self, user_id: str, content: str, category: str = "general",
                   embedding: bytes | None = None, metadata: dict[str, Any] | None = None) -> int:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO memories (user_id, content, category, embedding, metadata) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (user_id, content, category, embedding, json.dumps(metadata or {})),
                )
                row_id = cur.fetchone()[0]
            conn.commit()
        finally:
            self._release(conn)
        return row_id

    def get_memories(self, user_id: str, category: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if category:
                    cur.execute(
                        "SELECT id, content, category, created_at FROM memories "
                        "WHERE user_id = %s AND category = %s ORDER BY created_at DESC LIMIT %s",
                        (user_id, category, limit),
                    )
                else:
                    cur.execute(
                        "SELECT id, content, category, created_at FROM memories "
                        "WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                        (user_id, limit),
                    )
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
        finally:
            self._release(conn)
        return [dict(zip(cols, r)) for r in rows]

    def search_memories(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, user_id, content, category, created_at FROM memories "
                    "WHERE content ILIKE %s ORDER BY created_at DESC LIMIT %s",
                    (f"%{query}%", limit),
                )
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
        finally:
            self._release(conn)
        return [dict(zip(cols, r)) for r in rows]

    def get_memories_with_embeddings(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, content, category, embedding FROM memories "
                    "WHERE user_id = %s AND embedding IS NOT NULL ORDER BY created_at DESC LIMIT %s",
                    (user_id, limit),
                )
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
        finally:
            self._release(conn)
        return [dict(zip(cols, r)) for r in rows]

    def log_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int, cost_usd: float):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO cost_log (provider, model, input_tokens, output_tokens, cost_usd) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (provider, model, input_tokens, output_tokens, cost_usd),
                )
            conn.commit()
        finally:
            self._release(conn)

    def get_monthly_cost(self) -> float:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_log "
                    "WHERE created_at >= date_trunc('month', NOW())"
                )
                row = cur.fetchone()
        finally:
            self._release(conn)
        return float(row[0]) if row else 0.0

    def log_audit(self, user_id: str, action: str, detail: str | None = None, tier: int = 0):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_log (user_id, action, detail, tier) VALUES (%s, %s, %s, %s)",
                    (user_id, action, detail, tier),
                )
            conn.commit()
        finally:
            self._release(conn)

    def query_audit_log(
        self,
        where_clause: str = "",
        params: tuple = (),
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query the audit_log table with an optional WHERE clause.

        This is the safe public method for reading audit records — use it
        instead of accessing backend internals directly.
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                sql = "SELECT action, detail, user_id, created_at FROM audit_log"
                if where_clause:
                    sql += f" WHERE {where_clause}"
                sql += f" ORDER BY created_at DESC LIMIT {limit}"
                cur.execute(sql, params)
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
        finally:
            self._release(conn)
        return [dict(zip(cols, r)) for r in rows]

    def save_approval(
        self,
        request_id: str,
        request_type: str,
        description: str,
        proposed_change: dict[str, Any],
        status: str = "pending",
        resolved_at: str | None = None,
        resolved_by: str | None = None,
    ) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO approvals "
                    "(request_id, request_type, description, proposed_change, status, resolved_at, resolved_by) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (request_id) DO UPDATE SET "
                    "status = EXCLUDED.status, resolved_at = EXCLUDED.resolved_at, "
                    "resolved_by = EXCLUDED.resolved_by",
                    (request_id, request_type, description, json.dumps(proposed_change),
                     status, resolved_at, resolved_by),
                )
            conn.commit()
        finally:
            self._release(conn)

    def load_approvals(self, status: str | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if status:
                    cur.execute(
                        "SELECT * FROM approvals WHERE status = %s ORDER BY created_at DESC",
                        (status,),
                    )
                else:
                    cur.execute("SELECT * FROM approvals ORDER BY created_at DESC")
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
        finally:
            self._release(conn)
        results = []
        for r in rows:
            d = dict(zip(cols, r))
            d["proposed_change"] = json.loads(d.get("proposed_change") or "{}")
            results.append(d)
        return results


# ── Public facade ─────────────────────────────────────────────────────────────

class MemoryStore:
    """Auto-selects SQLite or PostgreSQL based on DATABASE_URL setting."""

    def __init__(self, db_path: Path | None = None):
        if settings.DATABASE_URL:
            logger.info("MemoryStore: connecting to PostgreSQL")
            self._backend: _SQLiteBackend | _PostgreSQLBackend = _PostgreSQLBackend(settings.DATABASE_URL)
        else:
            logger.info("MemoryStore: using SQLite at %s", db_path or settings.DB_PATH)
            self._backend = _SQLiteBackend(db_path or settings.DB_PATH)

    def close(self):
        self._backend.close()

    def get_or_create_conversation(self, conversation_id: str, channel: str, sender_id: str) -> str:
        return self._backend.get_or_create_conversation(conversation_id, channel, sender_id)

    def add_message(self, conversation_id: str, role: str, content: str,
                    channel: str | None = None, metadata: dict[str, Any] | None = None) -> int:
        return self._backend.add_message(conversation_id, role, content, channel, metadata)

    def get_conversation_history(self, conversation_id: str, limit: int = 20) -> list[dict[str, str]]:
        return self._backend.get_conversation_history(conversation_id, limit)

    def search_messages(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return self._backend.search_messages(query, limit)

    def add_memory(self, user_id: str, content: str, category: str = "general",
                   embedding: bytes | None = None, metadata: dict[str, Any] | None = None) -> int:
        return self._backend.add_memory(user_id, content, category, embedding, metadata)

    def get_memories(self, user_id: str, category: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        return self._backend.get_memories(user_id, category, limit)

    def search_memories(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return self._backend.search_memories(query, limit)

    def get_memories_with_embeddings(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return self._backend.get_memories_with_embeddings(user_id, limit)

    def log_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int, cost_usd: float):
        self._backend.log_cost(provider, model, input_tokens, output_tokens, cost_usd)

    def get_monthly_cost(self) -> float:
        return self._backend.get_monthly_cost()

    def log_audit(self, user_id: str, action: str, detail: str | None = None, tier: int = 0):
        self._backend.log_audit(user_id, action, detail, tier)

    def query_audit_log(
        self,
        where_clause: str = "",
        params: tuple = (),
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query audit_log records. Use this instead of accessing backend internals."""
        return self._backend.query_audit_log(where_clause, params, limit)

    def save_approval(
        self,
        request_id: str,
        request_type: str,
        description: str,
        proposed_change: dict[str, Any],
        status: str = "pending",
        resolved_at: str | None = None,
        resolved_by: str | None = None,
    ) -> None:
        """Persist an approval request (insert or update)."""
        self._backend.save_approval(
            request_id, request_type, description, proposed_change,
            status, resolved_at, resolved_by,
        )

    def load_approvals(self, status: str | None = None) -> list[dict[str, Any]]:
        """Load approval records, optionally filtered by status."""
        return self._backend.load_approvals(status)
