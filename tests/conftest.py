"""Offline substitutes and temporary-storage fixtures."""

import hashlib
from pathlib import Path

import pytest


class FakeEmbeddings:
    model_id = "test-embedding-v1"
    dimension = 16
    max_tokens = 32
    sends_text_externally = False

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts.copy())
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            for word in text.lower().split():
                digest = hashlib.sha256(word.encode("utf-8")).digest()
                vector[digest[0] % self.dimension] += 1.0
            if not any(vector):
                vector[0] = 1.0
            vectors.append(vector)
        return vectors


class RecordingTrace:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record(self, record: dict[str, object]) -> None:
        self.records.append(record.copy())


@pytest.fixture
def fake_embeddings() -> FakeEmbeddings:
    return FakeEmbeddings()


@pytest.fixture
def recording_trace() -> RecordingTrace:
    return RecordingTrace()


@pytest.fixture
def knowledge_dir(tmp_path: Path) -> Path:
    return tmp_path / "knowledge"
