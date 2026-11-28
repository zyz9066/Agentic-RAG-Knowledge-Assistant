from pathlib import Path

import pytest

from app.retrieval import (
    RetrievalError,
    new_operation_id,
    retrieve,
    retrieve_versioned,
)
from app.storage import Chunk, SQLiteKnowledgeStore


class Embeddings:
    model_id = "test-model"
    dimension = 2
    sends_text_externally = False

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def test_versioned_retrieval_binds_ranked_text_revision_and_digest(
    tmp_path: Path,
) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.replace(
        "facts.txt",
        "test-model",
        [
            Chunk("0", "less similar", (0.0, 1.0), 2),
            Chunk("1", "best", (1.0, 0.0), 3),
        ],
    )

    evidence = retrieve_versioned(
        store, Embeddings(), "question", 10, new_operation_id()
    )

    assert [(item.evidence.text, item.evidence.chunk_id) for item in evidence] == [
        ("best", "1"),
        ("less similar", "0"),
    ]
    assert all(item.revision and item.digest for item in evidence)
    assert [item.page for item in evidence] == [3, 2]


def test_versioned_retrieval_preserves_public_retrieve_shape(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.replace("facts.txt", "test-model", [Chunk("0", "fact", (1.0, 0.0), None)])

    public = retrieve(store, Embeddings(), "question", 5, new_operation_id())
    internal = retrieve_versioned(
        store, Embeddings(), "question", 5, new_operation_id()
    )

    assert public[0].__class__.__name__ == "Evidence"
    assert public[0].text == internal[0].evidence.text
    assert not hasattr(public[0], "revision")


def test_empty_index_is_distinct_and_incompatible_index_fails(
    tmp_path: Path,
) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    assert (
        retrieve_versioned(store, Embeddings(), "question", 5, new_operation_id()) == []
    )
    store.replace("facts.txt", "another-model", [Chunk("0", "fact", (1.0, 0.0), None)])
    with pytest.raises(RetrievalError):
        retrieve_versioned(store, Embeddings(), "question", 5, new_operation_id())
