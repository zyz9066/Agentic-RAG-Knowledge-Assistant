from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.ingestion import (
    ContentError,
    ExtractedPage,
    UploadEntry,
    chunk_pages,
    extract_pages,
    new_upload_batch,
    process_batch,
)
from app.storage import Chunk, SQLiteKnowledgeStore


def test_text_extracts_utf8_and_removes_only_initial_marker() -> None:
    pages = extract_pages(
        UploadEntry("facts.txt", b"\xef\xbb\xbfhello\xef\xbb\xbfworld")
    )
    assert pages == [ExtractedPage("hello\ufeffworld", None)]


def test_pdf_extracts_page_provenance() -> None:
    path = Path("data") / "sample-knowledge" / "observatory.pdf"
    pages = extract_pages(UploadEntry("facts.pdf", path.read_bytes()))
    assert pages
    assert all(page.page is not None and page.page >= 1 for page in pages)
    assert any("observatory" in page.text.lower() for page in pages)


def test_pdf_without_extractable_text_is_a_safe_failure() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = BytesIO()
    writer.write(output)
    with pytest.raises(ContentError, match="no extractable text"):
        extract_pages(UploadEntry("empty.pdf", output.getvalue()))


@pytest.mark.parametrize(
    "entry",
    [UploadEntry("empty.txt", b" "), UploadEntry("bad.pdf", b"not a pdf")],
)
def test_unreadable_content_raises_safe_error(entry: UploadEntry) -> None:
    with pytest.raises(ContentError) as error:
        extract_pages(entry)
    assert "not a pdf" not in str(error.value)


def test_chunking_respects_special_tokens_and_preserves_every_character() -> None:
    text = "abcdefghijklmnopqrstuvwxyz0123456789"
    pages = [ExtractedPage(text, 4)]
    chunks = chunk_pages(pages, lambda value: len(value) + 2, max_tokens=10)

    assert len(chunks) > 1
    assert all(len(chunk.text) + 2 <= 10 and chunk.page == 4 for chunk in chunks)
    covered = 0
    for chunk in chunks:
        start = text.index(chunk.text)
        assert start <= covered
        covered = max(covered, start + len(chunk.text))
    assert covered == len(text)


def test_chunking_fails_when_even_one_character_exceeds_model_limit() -> None:
    with pytest.raises(ContentError):
        chunk_pages([ExtractedPage("text", None)], lambda value: len(value) + 2, 2)


def test_chunking_keeps_long_whitespace_runs_without_gaps() -> None:
    text = "a" + " " * 25 + "b"
    chunks = chunk_pages([ExtractedPage(text, None)], lambda value: len(value) + 2, 8)
    assert any(chunk.text.isspace() for chunk in chunks)
    assert chunks[0].text.startswith("a")
    assert chunks[-1].text.endswith("b")


class LocalProvider:
    model_id = "test-model"
    dimension = 2
    max_tokens = 20
    sends_text_externally = False
    provider_id = "local"
    data_description = "local processing"

    def token_count(self, text: str) -> int:
        return len(text.split()) + 2

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def test_batch_processing_is_independent_and_preserves_failed_replacements(
    tmp_path: Path,
) -> None:
    class BrokenProvider(LocalProvider):
        def embed(self, texts: list[str]) -> list[list[float]]:
            if any("bad" in text for text in texts):
                raise RuntimeError("sensitive provider details")
            return super().embed(texts)

    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.replace("bad.txt", "test-model", [Chunk("0", "previous", (1.0, 0.0), None)])
    batch = new_upload_batch(
        [
            UploadEntry("bad.txt", b"bad"),
            UploadEntry("ok.txt", b"good"),
            UploadEntry("empty.txt", b""),
            UploadEntry("broken.pdf", b"not a pdf"),
        ]
    )
    transitions: list[tuple[str, str]] = []
    results = process_batch(
        batch,
        store,
        BrokenProvider(),
        on_status=lambda result: transitions.append((result.filename, result.status)),
    )

    assert [result.status for result in results] == [
        "failed",
        "indexed",
        "rejected",
        "failed",
    ]
    assert "sensitive provider details" not in results[0].message
    assert ("ok.txt", "processing") in transitions
    assert {
        (item.filename, item.text) for item in store.read_chunks("test-model", 2)
    } == {
        ("bad.txt", "previous"),
        ("ok.txt", "good"),
    }


def test_missing_provider_fails_without_losing_committed_data(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.replace("facts.txt", "test-model", [Chunk("0", "old", (1.0, 0.0), None)])
    result = process_batch(
        new_upload_batch([UploadEntry("facts.txt", b"new")]), store, None
    )[0]
    assert result.status == "failed"
    assert "provider" in result.message.lower()
    assert [item.text for item in store.read_chunks("test-model", 2)] == ["old"]


def test_reservation_errors_fail_before_processing_and_do_not_stop_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    reserve = store.reserve

    @contextmanager
    def broken_reservation(filename: str) -> Iterator[None]:
        if filename == "blocked.txt":
            raise OSError("sensitive path")
        with reserve(filename):
            yield

    monkeypatch.setattr(store, "reserve", broken_reservation)
    transitions: list[tuple[str, str]] = []
    results = process_batch(
        new_upload_batch(
            [UploadEntry("blocked.txt", b"secret"), UploadEntry("ok.txt", b"ok")]
        ),
        store,
        LocalProvider(),
        on_status=lambda result: transitions.append((result.filename, result.status)),
    )
    assert [result.status for result in results] == ["failed", "indexed"]
    assert ("blocked.txt", "processing") not in transitions
    assert "sensitive path" not in results[0].message


def test_reservation_conflict_is_a_retryable_rejection(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    with store.reserve("facts.txt"):
        result = process_batch(
            new_upload_batch([UploadEntry("facts.txt", b"new")]), store, LocalProvider()
        )[0]
    assert result.status == "rejected"
    assert "retry" in result.message.lower()
    assert store.read_chunks("test-model", 2) == []


def test_rejection_messages_explain_all_applicable_limits(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    results = process_batch(
        new_upload_batch(
            [UploadEntry("repeat.bin", b""), UploadEntry("repeat.bin", b"data")]
        ),
        store,
        LocalProvider(),
    )
    assert "duplicate" in results[0].message.lower()
    assert "empty" in results[0].message.lower()
    assert ".txt" in results[0].message
    oversized = new_upload_batch([UploadEntry(f"{i}.txt", b"x") for i in range(11)])
    assert "10" in process_batch(oversized, store, LocalProvider())[0].message


def test_validation_status_is_reported_before_validation_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    statuses: list[str] = []
    calls = 0

    def read_pdf(_stream: BytesIO) -> None:
        nonlocal calls
        if calls == 0:
            assert statuses == ["pending", "validating"]
        calls += 1
        raise ValueError("unreadable")

    monkeypatch.setattr("app.ingestion.PdfReader", read_pdf)
    result = process_batch(
        new_upload_batch([UploadEntry("bad.pdf", b"invalid")]),
        store,
        LocalProvider(),
        on_status=lambda item: statuses.append(item.status),
    )[0]
    assert result.status == "failed"
