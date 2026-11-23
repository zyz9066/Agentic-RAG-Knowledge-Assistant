import sqlite3
from pathlib import Path

import pytest

from app.storage import Chunk, SQLiteKnowledgeStore


def chunk(text: str, vector: tuple[float, ...] = (1.0, 0.0)) -> Chunk:
    return Chunk(chunk_id="0", text=text, embedding=vector, page=None)


def test_replacement_and_restart_preserve_provenance(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.sqlite3"
    store = SQLiteKnowledgeStore(path)
    store.replace("Facts.txt", "model-a", [chunk("old")])
    original_id = store.read_chunks("model-a", 2)[0].document_id
    store.replace("Facts.txt", "model-a", [Chunk("0", "new", (1.0, 0.0), 2)])
    store.replace("facts.txt", "model-a", [chunk("separate")])

    records = SQLiteKnowledgeStore(path).read_chunks("model-a", 2)
    assert {(item.filename, item.chunk_id, item.text) for item in records} == {
        ("Facts.txt", "0", "new"),
        ("facts.txt", "0", "separate"),
    }
    replaced = next(item for item in records if item.filename == "Facts.txt")
    assert replaced.document_id == original_id
    assert replaced.page == 2
    assert replaced.embedding == (1.0, 0.0)


def test_readers_see_only_committed_content(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.sqlite3"
    store = SQLiteKnowledgeStore(path)
    store.replace("facts.txt", "model-a", [chunk("old")])
    with sqlite3.connect(path) as writer:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("DELETE FROM chunks")
        assert [item.text for item in store.read_chunks("model-a", 2)] == ["old"]
        writer.rollback()

    assert [item.text for item in store.read_chunks("model-a", 2)] == ["old"]


def test_replacement_rolls_back_after_database_write_failure(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.sqlite3"
    store = SQLiteKnowledgeStore(path)
    store.replace("facts.txt", "model-a", [chunk("old")])
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_insert BEFORE INSERT ON chunks "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )

    with pytest.raises(sqlite3.IntegrityError):
        store.replace("facts.txt", "model-a", [chunk("new")])

    assert [item.text for item in store.read_chunks("model-a", 2)] == ["old"]


@pytest.mark.parametrize(
    "vector", [(0.0, 0.0), (float("nan"), 1.0), (float("inf"), 1.0)]
)
def test_invalid_vectors_do_not_replace_committed_content(
    tmp_path: Path, vector: tuple[float, ...]
) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.replace("facts.txt", "model-a", [chunk("old")])

    with pytest.raises(ValueError):
        store.replace("facts.txt", "model-a", [chunk("new", vector)])

    assert [item.text for item in store.read_chunks("model-a", 2)] == ["old"]


def test_incompatible_model_and_dimension_are_explicit_errors(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.replace("facts.txt", "model-a", [chunk("old")])

    with pytest.raises(ValueError, match="embedding"):
        store.replace("other.txt", "model-b", [chunk("other")])
    with pytest.raises(ValueError, match="embedding"):
        store.read_chunks("model-a", 3)


def test_whitespace_chunk_can_preserve_document_text(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.replace("facts.txt", "model-a", [chunk("   ")])
    assert store.read_chunks("model-a", 2)[0].text == "   "
