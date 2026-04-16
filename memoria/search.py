"""Busca híbrida: semântica + recência + reforço + relevância."""

import math
from datetime import UTC, datetime

import numpy as np

from memoria.config import RECENCY_HALF_LIFE_DAYS, SEARCH_WEIGHTS
from memoria.embeddings import bytes_to_embedding, generate_embedding
from memoria.models import Memory
from memoria.store import Store


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def recency_score(created_at: str) -> float:
    """Decay exponencial com half-life configurável."""
    try:
        created = datetime.fromisoformat(created_at.rstrip("Z"))
    except ValueError:
        return 0.5
    now = datetime.now(UTC).replace(tzinfo=None)
    days_ago = (now - created).total_seconds() / 86400
    return math.exp(-math.log(2) * days_ago / RECENCY_HALF_LIFE_DAYS)


def hybrid_score(
    semantic: float,
    recency: float,
    access_count: int,
    relevance: float,
) -> float:
    """Combina sinais com pesos configuráveis."""
    w = SEARCH_WEIGHTS
    reinforcement = min(1.0, math.log1p(access_count) / 3.0)
    return (
        w["semantic"] * semantic
        + w["recency"] * recency
        + w["reinforcement"] * reinforcement
        + w["relevance"] * relevance
    )


class MemoriaSearch:
    def __init__(self, store: Store):
        self.store = store

    def search(
        self,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
        layer: str | None = None,
        travessia: str | None = None,
    ) -> list[tuple[Memory, float]]:
        """Busca memórias por similaridade híbrida. Retorna (memory, score)."""
        query_embedding = generate_embedding(query)

        # Buscar todas as memórias com embedding
        all_memories = self.store.get_all_memories_with_embeddings()

        # Filtrar
        if memory_type:
            all_memories = [m for m in all_memories if m.memory_type == memory_type]
        if layer:
            all_memories = [m for m in all_memories if m.layer == layer]
        if travessia:
            all_memories = [m for m in all_memories if m.travessia == travessia]

        scored = []
        for mem in all_memories:
            mem_embedding = bytes_to_embedding(mem.embedding)
            sem_score = cosine_similarity(query_embedding, mem_embedding)
            rec_score = recency_score(mem.created_at)
            access_count = self.store.get_access_count(mem.id)
            score = hybrid_score(sem_score, rec_score, access_count, mem.relevance_score)
            scored.append((mem, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Log access para as memórias retornadas
        for mem, _ in scored[:limit]:
            self.store.log_access(mem.id, context=query[:200])

        return scored[:limit]
