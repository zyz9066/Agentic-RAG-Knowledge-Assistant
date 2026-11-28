"""Rank committed knowledge chunks as evidence without a relevance threshold."""

import math
import sqlite3
import threading
from collections import OrderedDict
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from app.observability import TraceOperation, WorkflowTracer
from app.storage import SQLiteKnowledgeStore, StoredChunk


class QueryEmbedder(Protocol):
    model_id: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class RetrievalError(ValueError):
    """A retrieval request could not be completed."""

    def __init__(self, message: str, code: str = "retrieval_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RetrievalDiagnostic:
    operation_id: str
    code: str
    message: str


class DiagnosticChannel:
    """Keep bounded, content-free warnings separately from evidence results."""

    def __init__(self, max_operations: int = 5000) -> None:
        self._max_operations = max_operations
        self._lock = threading.Lock()
        self._items: OrderedDict[str, list[RetrievalDiagnostic]] = OrderedDict()

    def record(self, operation_id: str, code: str, message: str) -> None:
        if not operation_id:
            return
        with self._lock:
            self._items.setdefault(operation_id, []).append(
                RetrievalDiagnostic(operation_id, code, message)
            )
            self._items.move_to_end(operation_id)
            while len(self._items) > self._max_operations:
                self._items.popitem(last=False)

    def get(self, operation_id: str) -> tuple[RetrievalDiagnostic, ...]:
        with self._lock:
            return tuple(self._items.get(operation_id, ()))


_diagnostics = DiagnosticChannel()


def get_diagnostics(operation_id: str) -> tuple[RetrievalDiagnostic, ...]:
    """Read warnings associated with a retrieval operation."""
    return _diagnostics.get(operation_id)


def record_diagnostic(operation_id: str, code: str, message: str) -> None:
    """Record a safe warning without changing a core operation outcome."""
    _diagnostics.record(operation_id, code, message)


@dataclass(frozen=True, slots=True)
class Evidence:
    text: str
    filename: str
    chunk_id: str
    score: float


@dataclass(frozen=True, slots=True)
class VersionedEvidence:
    evidence: Evidence
    document_id: str
    revision: str
    digest: str
    page: int | None


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
    *,
    tracer: WorkflowTracer | None = None,
) -> list[Evidence]:
    """Return up to limit ranked candidates from the committed index."""
    try:
        operation_context = (
            tracer.operation(
                operation_id,
                "retrieval",
                model_id=provider.model_id if provider is not None else None,
            )
            if tracer is not None
            else nullcontext(None)
        )
        with operation_context as operation:
            chunks = _retrieve_chunks(
                store, provider, question, limit, operation_id, operation
            )
            return [
                Evidence(chunk.text, chunk.filename, chunk.chunk_id, score)
                for chunk, score in chunks
            ]
    except RetrievalError as exc:
        record_diagnostic(operation_id, exc.code, str(exc))
        raise


def retrieve_versioned(
    store: SQLiteKnowledgeStore,
    provider: QueryEmbedder | None,
    question: str,
    limit: int,
    operation_id: str,
    *,
    tracer: WorkflowTracer | None = None,
) -> list[VersionedEvidence]:
    """Return ranked evidence bound to its committed source revision."""
    try:
        operation_context = (
            tracer.operation(
                operation_id,
                "retrieval",
                model_id=provider.model_id if provider is not None else None,
            )
            if tracer is not None
            else nullcontext(None)
        )
        with operation_context as operation:
            chunks = _retrieve_chunks(
                store, provider, question, limit, operation_id, operation
            )
            return [
                VersionedEvidence(
                    evidence=Evidence(
                        chunk.text, chunk.filename, chunk.chunk_id, score
                    ),
                    document_id=chunk.document_id,
                    revision=chunk.revision,
                    digest=chunk.digest,
                    page=chunk.page,
                )
                for chunk, score in chunks
            ]
    except RetrievalError as exc:
        record_diagnostic(operation_id, exc.code, str(exc))
        raise


def _retrieve_chunks(
    store: SQLiteKnowledgeStore,
    provider: QueryEmbedder | None,
    question: str,
    limit: int,
    operation_id: str,
    operation: TraceOperation | None,
) -> list[tuple[StoredChunk, float]]:
    with operation.step("input-validation") if operation else nullcontext():
        if (
            not isinstance(question, str)
            or not question.strip()
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit <= 0
            or not isinstance(operation_id, str)
            or not operation_id
        ):
            raise RetrievalError(
                "A question, positive result limit, and operation ID are required.",
                "invalid_input",
            )
        if provider is None:
            raise RetrievalError(
                "The embedding provider is unavailable.", "provider_unavailable"
            )
    try:
        with operation.step("query-embedding") if operation else nullcontext():
            vectors = provider.embed([question])
            if len(vectors) != 1:
                raise RetrievalError(
                    "The embedding provider returned an invalid result.",
                    "invalid_embedding",
                )
            query = _normalized(vectors[0], provider.dimension)
    except RetrievalError:
        raise
    except Exception:  # noqa: BLE001 - provider errors become safe retrieval failures.
        raise RetrievalError(
            "The embedding provider could not process the question.", "embedding_failed"
        ) from None
    try:
        with operation.step("evidence-lookup-ranking") if operation else nullcontext():
            chunks = store.read_chunks(provider.model_id, provider.dimension)
            evidence: list[tuple[StoredChunk, float]] = []
            for chunk in chunks:
                vector = _normalized(chunk.embedding, provider.dimension)
                score = math.fsum(left * right for left, right in zip(query, vector))
                evidence.append((chunk, score))
            evidence.sort(key=lambda item: item[1], reverse=True)
            return evidence[:limit]
    except RetrievalError:
        raise
    except (sqlite3.Error, OSError, ValueError):
        raise RetrievalError(
            "The knowledge index is unavailable or incompatible.",
            "storage_unavailable",
        ) from None
