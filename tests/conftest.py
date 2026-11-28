"""Offline substitutes and temporary-storage fixtures."""

import hashlib
import os
import socket
from pathlib import Path
from typing import Any

import pytest

os.environ["CREWAI_STORAGE_DIR"] = str(Path(__file__).parent / ".crewai-test-storage")
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
os.environ["CREWAI_TRACING_ENABLED"] = "false"
os.environ["OTEL_SDK_DISABLED"] = "true"


class FakeEmbeddings:
    model_id = "test-embedding-v1"
    dimension = 16
    max_tokens = 32
    sends_text_externally = False
    provider_id = "local-fake"
    data_description = "Document text is processed locally."

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def token_count(self, text: str) -> int:
        return len(text.split()) + 2

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


@pytest.fixture(autouse=True)
def deny_unapproved_network(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    original_connect = socket.socket.connect
    allow_loopback = request.node.get_closest_marker("allow_loopback") is not None
    credentialed = request.node.get_closest_marker("credentialed") is not None
    run_local_model = credentialed and os.environ.get("RUN_QUESTION_MODEL_TESTS") == "1"
    run_live_trace = (
        credentialed and os.environ.get("RUN_LANGFUSE_QUESTION_TESTS") == "1"
    )

    def refuse(sock: socket.socket, address: Any) -> object:
        if (
            allow_loopback
            and isinstance(address, tuple)
            and address
            and address[0] in {"127.0.0.1", "::1"}
            and len(address) > 1
            and isinstance(address[1], int)
            and address[1] >= 49152
        ):
            return original_connect(sock, address)
        if (
            run_local_model
            and isinstance(address, tuple)
            and len(address) > 1
            and address[0] == "127.0.0.1"
            and address[1] == 11434
        ):
            return original_connect(sock, address)
        if run_live_trace:
            return original_connect(sock, address)
        raise RuntimeError("test tried to use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
