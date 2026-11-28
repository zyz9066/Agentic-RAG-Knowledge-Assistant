from pathlib import Path
from typing import ClassVar

import pytest
from streamlit import config as streamlit_config
from streamlit.testing.v1 import AppTest

from app import embeddings
from app.question_workflow import AnswerOutcome, Citation, SupportedClaim
from app.retrieval import new_operation_id, retrieve_versioned
from app.storage import Chunk, SQLiteKnowledgeStore

pytestmark = pytest.mark.allow_loopback
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


@pytest.fixture(autouse=True)
def _loopback_streamlit_config():
    previous = streamlit_config.get_option("server.address")
    streamlit_config.set_option("server.address", "127.0.0.1")
    yield
    streamlit_config.set_option("server.address", previous)


def _configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STREAMLIT_SERVER_ADDRESS", "127.0.0.1")
    monkeypatch.setenv("KNOWLEDGE_DIR", str(tmp_path / "knowledge"))
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "models"))
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(embeddings, "LocalEmbeddings", StubLocalEmbeddings)


def test_ask_questions_is_separate_and_does_not_run_on_rerun(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure(monkeypatch, tmp_path)
    app = AppTest.from_file(str(_APP)).run()
    assert not app.exception

    app.segmented_control(key="app_view").set_value("Ask questions").run()

    assert not app.exception
    assert app.text_area(key="question_input")
    assert not app.button(key="submit_question").value


def test_blank_question_never_starts_a_workflow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure(monkeypatch, tmp_path)
    app = AppTest.from_file(str(_APP)).run()
    app.segmented_control(key="app_view").set_value("Ask questions").run()
    app.button(key="submit_question").click().run()

    assert not app.exception
    assert any("Enter a question" in item.value for item in app.info)


def test_input_edit_does_not_repeat_or_submit_question(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure(monkeypatch, tmp_path)
    app = AppTest.from_file(str(_APP)).run()
    app.segmented_control(key="app_view").set_value("Ask questions").run()
    app.text_area(key="question_input").set_value("A question").run()

    assert not app.exception
    assert not app.session_state.get("question_request_id")
    assert not app.button(key="submit_question").value


def test_displayed_claim_is_removed_after_source_changes_on_app_rerun(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure(monkeypatch, tmp_path)
    database = tmp_path / "knowledge" / "knowledge.sqlite3"
    store = SQLiteKnowledgeStore(database)
    store.replace(
        "facts.txt",
        "test-embedding-v1",
        [Chunk("0", "The lake is north.", (1.0,) + (0.0,) * 15, None)],
    )
    evidence = retrieve_versioned(
        store,
        StubLocalEmbeddings("unused", tmp_path),
        "Where is the lake?",
        5,
        new_operation_id(),
    )[0]
    citation = Citation(
        filename=evidence.evidence.filename,
        chunk_id=evidence.evidence.chunk_id,
        revision=evidence.revision,
        digest=evidence.digest,
        document_id=evidence.document_id,
    )
    app = AppTest.from_file(str(_APP)).run()
    app.segmented_control(key="app_view").set_value("Ask questions").run()
    app.session_state["question_request_id"] = "request"
    app.session_state["question_outcome"] = AnswerOutcome(
        status="complete",
        supported_claims=[
            SupportedClaim("The lake is north.", [citation]),
        ],
    )

    store.replace(
        "facts.txt",
        "test-embedding-v1",
        [Chunk("0", "The lake is south.", (1.0,) + (0.0,) * 15, None)],
    )
    app.run()

    outcome = app.session_state["question_outcome"]
    assert outcome.status == "abstained"
    assert outcome.supported_claims == []
    assert "source changed" in outcome.missing_explanation


def test_failed_outcome_renders_safe_guidance_and_operation_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure(monkeypatch, tmp_path)
    app = AppTest.from_file(str(_APP)).run()
    app.segmented_control(key="app_view").set_value("Ask questions").run()
    operation_id = "a" * 32
    app.session_state["question_request_id"] = operation_id
    app.session_state["question_outcome"] = AnswerOutcome(
        status="failed",
        error_code="workflow_failed",
    )

    app.run()

    assert not app.exception
    assert any("contact the maintainer" in item.value for item in app.error)
    assert any(operation_id in item.value for item in app.caption)
    assert all("workflow_failed" not in item.value for item in app.error)
