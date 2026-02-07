"""SQLite + FTS5 memory store for conversations, messages, and memories."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from openclaw.config import settings

logger = logging.getLogger(__name__)

_SCHEMA = """
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
"""


class MemoryStore:
    """Thread-safe SQLite store. Create one instance per worker."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or settings.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Conversations ────────────────────────────────────

    def get_or_create_conversation(
        self, conversation_id: str, channel: str, sender_id: str
    ) -> str:
        row = self.conn.execute(
            "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conversation_id,),
            )
            self.conn.commit()
            return conversation_id

        self.conn.execute(
            "INSERT INTO conversations (id, channel, sender_id) VALUES (?, ?, ?)",
            (conversation_id, channel, sender_id),
        )
        self.conn.commit()
        return conversation_id

    # ── Messages ─────────────────────────────────────────

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        channel: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO messages (conversation_id, role, content, channel, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, channel, json.dumps(metadata or {})),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_conversation_history(
        self, conversation_id: str, limit: int = 20
    ) -> list[dict[str, str]]:
        rows = self.conn.execute(
            "SELECT role, content FROM messages "
            "WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def search_messages(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT m.id, m.conversation_id, m.role, m.content, m.created_at "
            "FROM messages_fts fts "
            "JOIN messages m ON fts.rowid = m.id "
            "WHERE messages_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Memories ─────────────────────────────────────────

    def add_memory(
        self,
        user_id: str,
        content: str,
        category: str = "general",
        embedding: bytes | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO memories (user_id, content, category, embedding, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, content, category, embedding, json.dumps(metadata or {})),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_memories(
        self, user_id: str, category: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
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
        rows = self.conn.execute(
            "SELECT m.id, m.user_id, m.content, m.category, m.created_at "
            "FROM memories_fts fts "
            "JOIN memories m ON fts.rowid = m.id "
            "WHERE memories_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_memories_with_embeddings(
        self, user_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, content, category, embedding FROM memories "
            "WHERE user_id = ? AND embedding IS NOT NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Cost Tracking ────────────────────────────────────

    def log_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ):
        self.conn.execute(
            "INSERT INTO cost_log (provider, model, input_tokens, output_tokens, cost_usd) "
            "VALUES (?, ?, ?, ?, ?)",
            (provider, model, input_tokens, output_tokens, cost_usd),
        )
        self.conn.commit()

    def get_monthly_cost(self) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) as total FROM cost_log "
            "WHERE created_at >= date('now', 'start of month')"
        ).fetchone()
        return row["total"]

    # ── Audit ────────────────────────────────────────────

    def log_audit(
        self, user_id: str, action: str, detail: str | None = None, tier: int = 0
    ):
        self.conn.execute(
            "INSERT INTO audit_log (user_id, action, detail, tier) VALUES (?, ?, ?, ?)",
            (user_id, action, detail, tier),
        )
        self.conn.commit()
