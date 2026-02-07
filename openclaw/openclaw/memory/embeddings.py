"""Ollama-based embeddings with numpy cosine similarity."""

from __future__ import annotations

import logging
import struct
from typing import Any

import httpx
import numpy as np

from openclaw.config import settings

logger = logging.getLogger(__name__)


async def get_embedding(text: str) -> list[float] | None:
    """Get embedding vector from Ollama."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": settings.OLLAMA_EMBED_MODEL, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json().get("embedding")
    except Exception:
        logger.exception("Failed to get embedding")
        return None


def embedding_to_bytes(embedding: list[float]) -> bytes:
    """Pack float list to bytes for SQLite storage."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def bytes_to_embedding(data: bytes) -> np.ndarray:
    """Unpack bytes to numpy array."""
    n = len(data) // 4
    return np.array(struct.unpack(f"{n}f", data), dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


async def find_similar_memories(
    query: str,
    memories: list[dict[str, Any]],
    top_k: int = 5,
    threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """Find memories most similar to query using cosine similarity."""
    query_emb = await get_embedding(query)
    if query_emb is None:
        return []

    query_vec = np.array(query_emb, dtype=np.float32)
    scored = []

    for mem in memories:
        if mem.get("embedding") is None:
            continue
        mem_vec = bytes_to_embedding(mem["embedding"])
        score = cosine_similarity(query_vec, mem_vec)
        if score >= threshold:
            scored.append({**mem, "similarity": score})

    scored.sort(key=lambda m: m["similarity"], reverse=True)
    return scored[:top_k]
