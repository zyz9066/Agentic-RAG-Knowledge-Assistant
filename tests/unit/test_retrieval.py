import sqlite3
from pathlib import Path

import pytest

from app.observability import RecordingTraceSink, TraceDiagnosticChannel, WorkflowTracer
from app.retrieval import (
    RetrievalError,
    get_diagnostics,
    new_operation_id,
    retrieve,
)
from app.storage import Chunk, SQLiteKnowledgeStore


class Embeddings:
    model_id = "test-model"
    dimension = 2
    sends_text_externally = False

    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = [1.0, 0.0] if vector is None else vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.vector for _ in texts]


@pytest.fixture
def store(tmp_path: Path) -> SQLiteKnowledgeStore:
    return SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")


def test_ranked_results_include_only_evidence_and_provenance(
    store: SQLiteKnowledgeStore,
) -> None:
    store.replace(
        "facts.txt",
        "test-model",
        [
            Chunk("0", "less similar", (0.0, 1.0), 2),
            Chunk("1", "best", (1.0, 0.0), 3),
        ],
    )
    evidence = retrieve(store, Embeddings(), "question", 10, new_operation_id())
    assert [(item.text, item.filename, item.chunk_id) for item in evidence] == [
        ("best", "facts.txt", "1"),
        ("less similar", "facts.txt", "0"),
    ]
    assert [item.score for item in evidence] == pytest.approx([1.0, 0.0])
    assert len(retrieve(store, Embeddings(), "question", 1, new_operation_id())) == 1
    assert not hasattr(evidence[0], "operation_id")


def test_empty_index_and_unique_operation_identifiers(
    store: SQLiteKnowledgeStore,
) -> None:
    assert retrieve(store, Embeddings(), "question", 5, new_operation_id()) == []
    assert new_operation_id() != new_operation_id()


@pytest.mark.parametrize(
    ("question", "limit"), [("", 1), ("  ", 1), ("x", 0), ("x", -1)]
)
def test_invalid_requests_are_explicit(
    store: SQLiteKnowledgeStore, question: str, limit: int
) -> None:
    with pytest.raises(RetrievalError):
        retrieve(store, Embeddings(), question, limit, new_operation_id())


@pytest.mark.parametrize("vector", [[0.0, 0.0], [float("nan"), 1.0], [1.0]])
def test_invalid_query_vectors_are_explicit(
    store: SQLiteKnowledgeStore, vector: list[float]
) -> None:
    store.replace("facts.txt", "test-model", [Chunk("0", "fact", (1.0, 0.0), None)])
    with pytest.raises(RetrievalError):
        retrieve(store, Embeddings(vector), "question", 1, new_operation_id())


def test_incompatible_model_is_not_an_empty_success(
    store: SQLiteKnowledgeStore,
) -> None:
    store.replace(
        "facts.txt", "different-model", [Chunk("0", "fact", (1.0, 0.0), None)]
    )
    with pytest.raises(RetrievalError):
        retrieve(store, Embeddings(), "question", 1, new_operation_id())


def test_storage_failure_is_safe_and_explicit(
    store: SQLiteKnowledgeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_model: str, _dimension: int) -> list[object]:
        raise sqlite3.OperationalError("sensitive path")

    monkeypatch.setattr(store, "read_chunks", fail)
    with pytest.raises(RetrievalError) as error:
        retrieve(store, Embeddings(), "question", 1, new_operation_id())
    assert "sensitive path" not in str(error.value)


def test_missing_or_failing_provider_is_not_an_empty_success(
    store: SQLiteKnowledgeStore,
) -> None:
    store.replace("facts.txt", "test-model", [Chunk("0", "fact", (1.0, 0.0), None)])

    class BrokenEmbeddings(Embeddings):
        def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("sensitive provider detail")

    with pytest.raises(RetrievalError):
        retrieve(store, None, "question", 1, new_operation_id())
    with pytest.raises(RetrievalError) as error:
        retrieve(store, BrokenEmbeddings(), "question", 1, new_operation_id())
    assert "sensitive provider detail" not in str(error.value)


def test_diagnostics_correlate_errors_without_changing_results(
    store: SQLiteKnowledgeStore,
) -> None:
    operation_id = new_operation_id()
    with pytest.raises(RetrievalError):
        retrieve(store, Embeddings(), "  ", 2, operation_id)
    diagnostic = get_diagnostics(operation_id)
    assert len(diagnostic) == 1
    assert diagnostic[0].code == "invalid_input"
    assert (
        diagnostic[0].message
        == "A question, positive result limit, and operation ID are required."
    )


def test_concurrent_diagnostics_keep_operation_ids_separate(
    store: SQLiteKnowledgeStore,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    identifiers = [new_operation_id(), new_operation_id()]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(retrieve, store, Embeddings(), question, 1, identifier)
            for question, identifier in zip(["", "  "], identifiers)
        ]
        for future in futures:
            with pytest.raises(RetrievalError):
                future.result()
    assert all(
        [item.operation_id for item in get_diagnostics(identifier)] == [identifier]
        for identifier in identifiers
    )


def test_retrieval_trace_contains_steps_but_not_question_or_evidence(
    store: SQLiteKnowledgeStore,
) -> None:
    store.replace(
        "secret-name.txt",
        "test-model",
        [Chunk("0", "PRIVATE_EVIDENCE", (1.0, 0.0), None)],
    )
    sink = RecordingTraceSink()
    tracer = WorkflowTracer(sink, TraceDiagnosticChannel())
    identifier = new_operation_id()
    evidence = retrieve(
        store,
        Embeddings(),
        "PRIVATE_QUESTION",
        1,
        identifier,
        tracer=tracer,
    )
    assert evidence[0].text == "PRIVATE_EVIDENCE"
    assert [step.name for step in sink.records[0].steps] == [
        "input-validation",
        "query-embedding",
        "evidence-lookup-ranking",
    ]
    assert "PRIVATE_QUESTION" not in repr(sink.records[0])
    assert "PRIVATE_EVIDENCE" not in repr(sink.records[0])
    assert "secret-name.txt" not in repr(sink.records[0])
