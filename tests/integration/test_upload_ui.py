from pathlib import Path
from typing import ClassVar

import pytest
from streamlit import config as streamlit_config
from streamlit.testing.v1 import AppTest

from app import embeddings
from app.storage import SQLiteKnowledgeStore

_APP = Path(__file__).parents[2] / "app" / "ui.py"


class StubLocalEmbeddings:
    model_id = "test-embedding-v1"
    dimension = 16
    max_tokens = 32
    sends_text_externally = False
    provider_id = "local-fake"
    data_description = "Document text is processed locally."
    instances: ClassVar[list["StubLocalEmbeddings"]] = []

    def __init__(self, _model_name: str, _cache_dir: Path) -> None:
        self.calls: list[list[str]] = []
        self.instances.append(self)

    def token_count(self, text: str) -> int:
        return len(text.split()) + 2

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts.copy())
        return [[1.0] + [0.0] * (self.dimension - 1) for _ in texts]


class StubExternalEmbeddings(StubLocalEmbeddings):
    sends_text_externally = True
    provider_id = "external-test-provider"
    data_description = "Document text is sent to an external test provider."


def _set_local_app_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    knowledge_dir = tmp_path / "knowledge"
    monkeypatch.setenv("STREAMLIT_SERVER_ADDRESS", "127.0.0.1")
    monkeypatch.setenv("KNOWLEDGE_DIR", str(knowledge_dir))
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "models"))
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    return knowledge_dir


def _rendered_text(app: AppTest) -> list[str]:
    return [str(getattr(item, "value", "")) for item in app.get("text")]


@pytest.fixture(autouse=True)
def _loopback_streamlit_config():
    previous = streamlit_config.get_option("server.address")
    streamlit_config.set_option("server.address", "127.0.0.1")
    yield
    streamlit_config.set_option("server.address", previous)


def test_upload_snapshot_is_not_resubmitted_on_rerun(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    knowledge_dir = _set_local_app_environment(monkeypatch, tmp_path)
    StubLocalEmbeddings.instances.clear()
    monkeypatch.setattr(embeddings, "LocalEmbeddings", StubLocalEmbeddings)

    app = AppTest.from_file(str(_APP)).run()
    assert not app.exception
    app.file_uploader[0].upload("facts.txt", b"private evidence")
    app.button(key="submit_uploads").click().run()

    assert not app.exception
    assert any(
        "facts.txt: indexed - File indexed." in text for text in _rendered_text(app)
    )
    store = SQLiteKnowledgeStore(knowledge_dir / "knowledge.sqlite3")
    assert [chunk.text for chunk in store.read_chunks("test-embedding-v1", 16)] == [
        "private evidence"
    ]

    app.run()
    assert not app.exception
    assert any(
        "facts.txt: indexed - File indexed." in text for text in _rendered_text(app)
    )
    assert len(StubLocalEmbeddings.instances[-1].calls) == 1
    assert len(store.read_chunks("test-embedding-v1", 16)) == 1


def test_unsupported_upload_is_rejected_without_loading_the_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_local_app_environment(monkeypatch, tmp_path)
    StubLocalEmbeddings.instances.clear()
    monkeypatch.setattr(embeddings, "LocalEmbeddings", StubLocalEmbeddings)

    app = AppTest.from_file(str(_APP)).run()
    app.file_uploader[0].upload("facts.csv", b"private evidence")
    app.button(key="submit_uploads").click().run()

    assert not app.exception
    result = app.session_state["upload_results"][0]
    assert result.status == "rejected"
    assert result.reasons == ("type",)
    assert StubLocalEmbeddings.instances == []


def test_mixed_upload_shows_independent_statuses_and_can_be_resubmitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    knowledge_dir = _set_local_app_environment(monkeypatch, tmp_path)
    StubLocalEmbeddings.instances.clear()
    monkeypatch.setattr(embeddings, "LocalEmbeddings", StubLocalEmbeddings)

    app = AppTest.from_file(str(_APP)).run()
    app.file_uploader[0].upload("facts.csv", b"unsupported evidence")
    app.file_uploader[0].upload("facts.txt", b"supported evidence")
    app.button(key="submit_uploads").click().run()

    assert not app.exception
    rendered = "\n".join(_rendered_text(app))
    assert "facts.csv: rejected" in rendered
    assert "facts.txt: indexed" in rendered

    store = SQLiteKnowledgeStore(knowledge_dir / "knowledge.sqlite3")
    assert [chunk.text for chunk in store.read_chunks("test-embedding-v1", 16)] == [
        "supported evidence"
    ]

    app.run()
    assert not app.exception
    assert "facts.txt: indexed" in "\n".join(_rendered_text(app))


def test_external_indexing_has_no_consent_after_a_streamlit_rerun(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_local_app_environment(monkeypatch, tmp_path)
    StubExternalEmbeddings.instances.clear()
    monkeypatch.setattr(embeddings, "LocalEmbeddings", StubExternalEmbeddings)

    app = AppTest.from_file(str(_APP)).run()
    app.file_uploader[0].upload("facts.txt", b"private evidence")
    app.button(key="submit_uploads").click().run()

    result = app.session_state["upload_results"][0]
    assert result.status == "failed"
    assert "requires consent" in result.message.lower()
    assert StubExternalEmbeddings.instances[-1].calls == []

    app.run()
    assert StubExternalEmbeddings.instances[-1].calls == []
    assert [
        item.text
        for item in SQLiteKnowledgeStore(
            tmp_path / "knowledge" / "knowledge.sqlite3"
        ).read_chunks("test-embedding-v1", 16)
    ] == []


def test_trace_consent_is_separate_and_external_export_starts_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_local_app_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("LANGFUSE_HOST", "https://trace.example")

    app = AppTest.from_file(str(_APP)).run()

    assert not app.exception
    assert app.checkbox(key="external_trace_consent")
    assert any("External trace export is disabled" in item.value for item in app.info)
    assert any(
        "No external indexing provider is configured" in item.value for item in app.info
    )
    assert app.button(key="enable_external_trace_export").proto.disabled


def test_local_trace_confirmation_discloses_process_lifetime_and_forwarding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_local_app_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("LANGFUSE_HOST", "http://127.0.0.1:3000")

    app = AppTest.from_file(str(_APP)).run()

    assert not app.exception
    assert app.checkbox(key="local_trace_attestation")
    assert app.button(key="confirm_local_trace").proto.disabled
    assert app.button(key="revoke_local_trace")
    rendered = "\n".join(_rendered_text(app))
    assert "process" in rendered
    assert "forwarding configuration" in rendered


def test_loopback_binding_fails_closed_for_unset_and_non_loopback_addresses() -> None:
    previous = streamlit_config.get_option("server.address")
    streamlit_config.set_option("server.address", "0.0.0.0")
    try:
        app = AppTest.from_file(str(_APP)).run()
    finally:
        streamlit_config.set_option("server.address", previous)

    assert not app.exception
    assert any("Unsafe or unset server binding" in item.value for item in app.error)
    assert not app.file_uploader
