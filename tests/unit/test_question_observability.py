from pathlib import Path

from app.evaluation import (
    EvaluationSourceVerifier,
    load_evaluation_cases,
)
from app.ingestion import UploadEntry, chunk_pages, extract_pages
from app.observability import (
    EvaluationTracePayload,
    RecordingTraceSink,
    TraceDiagnosticChannel,
    TraceExportStatus,
    TracePermissionManager,
    TraceRecord,
    WorkflowTracer,
)
from app.retrieval import new_operation_id
from app.storage import Chunk, SQLiteKnowledgeStore

_CASE_FILE = Path(__file__).parents[2] / "evaluation" / "feature_002" / "cases.jsonl"


class _TextEmbeddings:
    model_id = "evaluation-model"
    dimension = 2
    max_tokens = 512
    sends_text_externally = False
    provider_id = "deterministic-test"
    data_description = "Test text is processed locally."

    def token_count(self, text: str) -> int:
        return len(text)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def _index_source(store: SQLiteKnowledgeStore, source_dir: Path, filename: str) -> None:
    data = (source_dir / filename).read_bytes()
    pages = extract_pages(UploadEntry(filename, data))
    pieces = chunk_pages(pages, _TextEmbeddings().token_count, 512)
    store.replace(
        filename,
        _TextEmbeddings.model_id,
        [
            Chunk(str(index), piece.text, (1.0, 0.0), piece.page)
            for index, piece in enumerate(pieces)
        ],
    )


def test_question_trace_is_content_free_and_records_allowlisted_stages() -> None:
    sink = RecordingTraceSink()
    diagnostics = TraceDiagnosticChannel()
    tracer = WorkflowTracer(sink, diagnostics)
    operation_id = new_operation_id()

    with tracer.operation(operation_id, "question") as operation:
        with operation.step("retrieval"):
            pass
        with operation.step("drafting"):
            pass
        with operation.step("verification"):
            pass

    record = sink.records[0]
    assert [step.name for step in record.steps] == [
        "retrieval",
        "drafting",
        "verification",
    ]
    assert "PRIVATE_QUESTION" not in repr(record)
    assert "PRIVATE_DOCUMENT" not in repr(record)


def test_unconfirmed_delivery_is_not_reported_as_confirmed() -> None:
    class UnconfirmedSink:
        def export(self, record: TraceRecord) -> TraceExportStatus:
            return "unconfirmed"

    diagnostics = TraceDiagnosticChannel()
    with WorkflowTracer(UnconfirmedSink(), diagnostics).operation(
        new_operation_id(), "question"
    ):
        pass

    warnings = diagnostics.get(next(iter(diagnostics._items)))
    assert warnings[0].code == "trace_unconfirmed"


def test_evaluation_payload_requires_dispatch_authorization(tmp_path: Path) -> None:
    from app.observability import EvaluationTracePayload, TracePermissionManager

    manager = TracePermissionManager(
        tmp_path / "permissions.sqlite3", "https://trace.example"
    )
    payload = EvaluationTracePayload(
        case_id="case-1",
        question="Known evaluation question?",
        source_ids=(("known.txt", "0"),),
        fields_confirmed=True,
    )
    record = TraceRecord(
        operation_id=new_operation_id(),
        name="question",
        status="success",
        duration_ms=1,
        model_id=None,
        steps=(),
        evaluation_payload=payload,
    )
    sent: list[TraceRecord] = []
    assert not manager.dispatch(record, lambda current, _dest: sent.append(current))
    assert sent == []


def test_evaluation_source_must_match_complete_bundled_document(
    tmp_path: Path,
) -> None:
    source_dir = _CASE_FILE.parent / "sources"
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    _index_source(store, source_dir, "orchard.txt")
    cases = load_evaluation_cases(_CASE_FILE)
    verifier = EvaluationSourceVerifier(store, _TextEmbeddings(), cases, source_dir)
    payload = EvaluationTracePayload(
        case_id="orchard-hives",
        question="How many beehives does Cedar Grove Orchard maintain?",
        source_ids=(("orchard.txt", "0"),),
        fields_confirmed=True,
    )

    with verifier.dispatch_eligibility(payload) as eligible:
        assert eligible

    store.replace(
        "orchard.txt",
        _TextEmbeddings.model_id,
        [Chunk("0", "Private replacement.", (1.0, 0.0), None)],
    )
    with verifier.dispatch_eligibility(payload) as eligible:
        assert not eligible


def test_evaluation_fields_are_sent_only_after_confirmation_and_eligibility(
    tmp_path: Path,
) -> None:
    source_dir = _CASE_FILE.parent / "sources"
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    _index_source(store, source_dir, "orchard.txt")
    verifier = EvaluationSourceVerifier(
        store, _TextEmbeddings(), load_evaluation_cases(_CASE_FILE), source_dir
    )
    manager = TracePermissionManager(
        tmp_path / "permissions.sqlite3", "https://trace.example"
    )
    manager.grant_external()
    payload = EvaluationTracePayload(
        case_id="orchard-hives",
        question="How many beehives does Cedar Grove Orchard maintain?",
        source_ids=(("orchard.txt", "0"),),
        fields_confirmed=True,
    )
    record = TraceRecord(
        operation_id=new_operation_id(),
        name="question",
        status="success",
        duration_ms=1,
        model_id=None,
        steps=(),
        evaluation_payload=payload,
    )
    sent: list[TraceRecord] = []

    assert manager.dispatch(
        record,
        lambda current, _dest: sent.append(current),
        evaluation_eligibility=verifier.dispatch_eligibility,
    )
    assert sent[0].evaluation_payload == payload
