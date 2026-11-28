import sqlite3
from pathlib import Path

import pytest

from app.storage import Chunk, SQLiteKnowledgeStore


def _chunk(text: str, *, page: int | None = None) -> Chunk:
    return Chunk("0", text, (1.0, 0.0), page)


def _legacy_store(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE index_metadata (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                embedding_model_id TEXT NOT NULL,
                embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension > 0)
            );
            CREATE TABLE documents (
                document_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE COLLATE BINARY,
                indexed_at TEXT NOT NULL,
                embedding_model_id TEXT NOT NULL,
                embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension > 0)
            );
            CREATE TABLE chunks (
                document_id TEXT NOT NULL REFERENCES documents(document_id)
                    ON DELETE CASCADE,
                chunk_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                text TEXT NOT NULL,
                embedding BLOB NOT NULL,
                page INTEGER,
                PRIMARY KEY (document_id, chunk_id)
            );
            INSERT INTO index_metadata VALUES (1, 'model-a', 2);
            INSERT INTO documents VALUES ('doc-1', 'facts.txt', 'now', 'model-a', 2);
            INSERT INTO chunks VALUES ('doc-1', '0', 0, 'old', x'0000803f00000000', NULL);
            """
        )


def test_existing_rows_receive_revisions_without_losing_chunks(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.sqlite3"
    _legacy_store(path)

    store = SQLiteKnowledgeStore(path)
    chunks = store.read_chunks("model-a", 2)

    assert len(chunks) == 1
    assert chunks[0].document_id == "doc-1"
    assert chunks[0].text == "old"
    assert chunks[0].revision
    assert chunks[0].digest
    assert SQLiteKnowledgeStore(path).read_chunks("model-a", 2)[0].revision == (
        chunks[0].revision
    )


def test_identical_replacement_mints_revision_and_failed_replace_rolls_back(
    tmp_path: Path,
) -> None:
    path = tmp_path / "knowledge.sqlite3"
    store = SQLiteKnowledgeStore(path)
    store.replace("facts.txt", "model-a", [_chunk("same")])
    original = store.read_chunks("model-a", 2)[0]

    store.replace("facts.txt", "model-a", [_chunk("same")])
    replacement = store.read_chunks("model-a", 2)[0]
    assert replacement.revision != original.revision
    assert replacement.digest == original.digest

    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_insert BEFORE INSERT ON chunks "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.replace("facts.txt", "model-a", [_chunk("failed")])

    current = store.read_chunks("model-a", 2)[0]
    assert current.revision == replacement.revision
    assert current.text == "same"


def test_versioned_snapshot_binds_text_revision_and_page(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.replace("facts.txt", "model-a", [_chunk("fact", page=3)])

    chunk = store.read_chunks("model-a", 2)[0]

    assert chunk.revision
    assert chunk.digest
    assert chunk.page == 3


def test_freshness_checks_all_citations_against_one_committed_snapshot(
    tmp_path: Path,
) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.replace("facts.txt", "model-a", [_chunk("old")])
    old = store.read_chunks("model-a", 2)[0]

    assert store.citations_are_current([old]) == [True]
    store.replace("facts.txt", "model-a", [_chunk("new")])
    assert store.citations_are_current([old]) == [False]
