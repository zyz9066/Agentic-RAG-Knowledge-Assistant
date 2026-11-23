from pathlib import Path

from app.ingestion import (
    UploadEntry,
    describe_provider,
    grant_indexing_consent,
    new_upload_batch,
    process_batch,
)
from app.storage import SQLiteKnowledgeStore


class RecordingExternalProvider:
    model_id = "recording-model"
    dimension = 2
    max_tokens = 32
    sends_text_externally = True
    provider_id = "external-service-a"
    data_description = "Document text will be sent to external-service-a."

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def token_count(self, text: str) -> int:
        return len(text.split()) + 2

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[1.0, 0.0] for _ in texts]


def test_external_indexing_requires_consent_for_each_batch_and_provider(
    tmp_path: Path,
) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    provider = RecordingExternalProvider()
    first = new_upload_batch([UploadEntry("facts.txt", b"private document")])
    disclosure = describe_provider(provider)
    assert provider.provider_id in disclosure
    assert provider.data_description in disclosure
    refusal = process_batch(first, store, provider)[0]
    assert refusal.status == "failed"
    assert "consent" in refusal.message.lower()
    assert provider.calls == []

    consent = grant_indexing_consent(first, provider)
    assert process_batch(first, store, provider, consent=consent)[0].status == "indexed"
    assert provider.calls == [["private document"]]

    second = new_upload_batch([UploadEntry("other.txt", b"other private document")])
    assert process_batch(second, store, provider, consent=consent)[0].status == "failed"
    changed = RecordingExternalProvider()
    changed.provider_id = "external-service-b"
    assert process_batch(first, store, changed, consent=consent)[0].status == "failed"
    assert provider.calls == [["private document"]]
    assert changed.calls == []


def test_missing_external_disclosure_cannot_authorize_text_transfer(
    tmp_path: Path,
) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    provider = RecordingExternalProvider()
    provider.data_description = ""
    batch = new_upload_batch([UploadEntry("facts.txt", b"private document")])
    consent = grant_indexing_consent(batch, provider)
    assert process_batch(batch, store, provider, consent=consent)[0].status == "failed"
    assert provider.calls == []


def test_changed_disclosure_requires_new_consent(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    provider = RecordingExternalProvider()
    batch = new_upload_batch([UploadEntry("facts.txt", b"private document")])
    consent = grant_indexing_consent(batch, provider)
    provider.data_description = "Different data will be sent to the same service."
    assert process_batch(batch, store, provider, consent=consent)[0].status == "failed"
    assert provider.calls == []
