"""Session and conversation context management."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from openclaw.memory.embeddings import find_similar_memories
from openclaw.memory.store import MemoryStore

logger = logging.getLogger(__name__)


def build_conversation_id(channel: str, sender_id: str) -> str:
    """Deterministic conversation ID from channel + sender."""
    raw = f"{channel}:{sender_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def get_context_for_message(
    store: MemoryStore,
    conversation_id: str,
    sender_id: str,
    query: str,
    history_limit: int = 10,
    memory_limit: int = 5,
) -> dict[str, Any]:
    """Build full context for an incoming message.

    Returns conversation history and relevant memories.
    """
    history = store.get_conversation_history(conversation_id, limit=history_limit)

    # Try semantic search first, fall back to FTS
    memories_with_emb = store.get_memories_with_embeddings(sender_id, limit=100)
    if memories_with_emb:
        similar = await find_similar_memories(
            query, memories_with_emb, top_k=memory_limit
        )
        memory_texts = [m["content"] for m in similar]
    else:
        fts_results = store.search_memories(query, limit=memory_limit)
        memory_texts = [m["content"] for m in fts_results]

    return {
        "conversation_history": history,
        "memories": memory_texts,
    }
