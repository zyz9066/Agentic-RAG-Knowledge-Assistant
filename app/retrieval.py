"""Rank committed knowledge chunks as evidence without a relevance threshold."""

import math
import sqlite3
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from app.storage import SQLiteKnowledgeStore


class QueryEmbedder(Protocol):
    model_id: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class RetrievalError(ValueError):
    """A retrieval request could not be completed."""


@dataclass(frozen=True, slots=True)
class Evidence:
    text: str
    filename: str
    chunk_id: str
    score: float


def new_operation_id() -> str:
    """Allocate an opaque identifier before entering retrieval."""
    return uuid4().hex


def _normalized(vector: list[float] | tuple[float, ...], dimension: int) -> list[float]:
    if len(vector) != dimension or not all(math.isfinite(value) for value in vector):
        raise RetrievalError("The embedding is invalid or incompatible.")
    magnitude = math.hypot(*vector)
    if not math.isfinite(magnitude) or magnitude == 0:
        raise RetrievalError("The embedding is invalid or incompatible.")
    return [value / magnitude for value in vector]


def retrieve(
    store: SQLiteKnowledgeStore,
    provider: QueryEmbedder | None,
    question: str,
    limit: int,
    operation_id: str,
) -> list[Evidence]:
    """Return up to limit ranked candidates from the committed index."""
    if (
        not question.strip()
        or isinstance(limit, bool)
        or limit <= 0
        or not operation_id
    ):
        raise RetrievalError(
            "A question, positive result limit, and operation ID are required."
        )
    if provider is None:
        raise RetrievalError("The embedding provider is unavailable.")
    try:
        chunks = store.read_chunks(provider.model_id, provider.dimension)
    except (sqlite3.Error, OSError, ValueError):
        raise RetrievalError(
            "The knowledge index is unavailable or incompatible."
        ) from None
    if not chunks:
        return []
    try:
        vectors = provider.embed([question])
    except (OSError, RuntimeError, ValueError):
        raise RetrievalError(
            "The embedding provider could not process the question."
        ) from None
    if len(vectors) != 1:
        raise RetrievalError("The embedding provider returned an invalid result.")
    query = _normalized(vectors[0], provider.dimension)
    evidence: list[Evidence] = []
    for chunk in chunks:
        vector = _normalized(chunk.embedding, provider.dimension)
        score = math.fsum(left * right for left, right in zip(query, vector))
        evidence.append(Evidence(chunk.text, chunk.filename, chunk.chunk_id, score))
    evidence.sort(key=lambda item: item.score, reverse=True)
    return evidence[:limit]
