import time

from app.observability import (
    LangfuseTraceSink,
    RecordingTraceSink,
    TraceDiagnosticChannel,
    TracePermissionManager,
    TraceRecord,
    TraceStep,
    WorkflowTracer,
)


def test_operation_records_hierarchy_outcomes_duration_and_allowlisted_metadata() -> (
    None
):
    sink = RecordingTraceSink()
    diagnostics = TraceDiagnosticChannel()
    tracer = WorkflowTracer(sink, diagnostics)
    operation_id = "a" * 32

    with tracer.operation(
        operation_id, "indexing", model_id="test-model@revision-1"
    ) as operation:
        with operation.step("validation"):
            time.sleep(0.001)
        with operation.step("embedding", usage_details={"input_tokens": 5}):
            pass

    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.operation_id == operation_id
    assert record.name == "indexing"
    assert record.status == "success"
    assert record.duration_ms >= 0
    assert [step.name for step in record.steps] == ["validation", "embedding"]
    assert all(step.parent_id == operation_id for step in record.steps)
    assert all(step.duration_ms >= 0 for step in record.steps)
    assert record.steps[1].usage_details == {"input_tokens": 5}
    assert record.model_id == "test-model@revision-1"
    assert diagnostics.get(operation_id) == ()


def test_failed_operation_does_not_capture_exception_text() -> None:
    sink = RecordingTraceSink()
    tracer = WorkflowTracer(sink, TraceDiagnosticChannel())
    operation_id = "b" * 32

    try:
        with (
            tracer.operation(operation_id, "retrieval") as operation,
            operation.step("query-embedding"),
        ):
            raise RuntimeError("PRIVATE_DOCUMENT_SENTINEL")
    except RuntimeError:
        pass

    record = sink.records[0]
    assert record.status == "failed"
    assert record.steps[0].status == "failed"
    assert "PRIVATE_DOCUMENT_SENTINEL" not in repr(record)


def test_export_failure_becomes_safe_diagnostic_not_core_failure() -> None:
    class BrokenSink:
        def export(self, record: TraceRecord) -> None:
            raise RuntimeError("PRIVATE_DOCUMENT_SENTINEL")

    diagnostics = TraceDiagnosticChannel()
    tracer = WorkflowTracer(BrokenSink(), diagnostics)
    operation_id = "c" * 32
    with tracer.operation(operation_id, "retrieval"):
        pass
    warnings = diagnostics.get(operation_id)
    assert len(warnings) == 1
    assert warnings[0].code == "trace_export_failed"
    assert "PRIVATE_DOCUMENT_SENTINEL" not in warnings[0].message


def test_core_exception_survives_simultaneous_trace_export_failure() -> None:
    class BrokenSink:
        def export(self, record: TraceRecord) -> None:
            raise RuntimeError("trace transport detail")

    diagnostics = TraceDiagnosticChannel()
    tracer = WorkflowTracer(BrokenSink(), diagnostics)
    operation_id = "1" * 32
    try:
        with tracer.operation(operation_id, "retrieval"):
            raise ValueError("core failure")
    except ValueError as error:
        assert str(error) == "core failure"
    else:
        raise AssertionError("core failure must be propagated")
    assert diagnostics.get(operation_id)[0].code == "trace_export_failed"


def test_missing_trace_sink_produces_an_explicit_warning() -> None:
    diagnostics = TraceDiagnosticChannel()
    tracer = WorkflowTracer(None, diagnostics)
    operation_id = "2" * 32
    with tracer.operation(operation_id, "retrieval"):
        pass
    assert diagnostics.get(operation_id)[0].code == "trace_unavailable"


def test_invalid_operation_ids_are_not_exported() -> None:
    sink = RecordingTraceSink()
    tracer = WorkflowTracer(sink, TraceDiagnosticChannel())
    with tracer.operation("not-opaque", "retrieval"):
        pass
    assert sink.records == []


def test_langfuse_sink_does_not_construct_client_without_permission(
    tmp_path, monkeypatch
) -> None:
    manager = TracePermissionManager(
        tmp_path / "permissions.sqlite3", "https://trace.example"
    )
    diagnostics = TraceDiagnosticChannel()

    def forbidden_client(**_kwargs: object) -> None:
        raise AssertionError("Langfuse must not be constructed before authorization")

    monkeypatch.setattr("app.observability.Langfuse", forbidden_client)
    sink = LangfuseTraceSink(
        manager,
        diagnostics,
        public_key="public",
        secret_key="secret",
    )
    sink.export(
        TraceRecord(
            operation_id="e" * 32,
            name="retrieval",
            status="success",
            duration_ms=1,
            model_id=None,
            steps=(),
        )
    )
    assert diagnostics.get("e" * 32)[0].code == "trace_disabled"


def test_langfuse_sink_sanitizes_manually_constructed_records(
    tmp_path, monkeypatch
) -> None:
    manager = TracePermissionManager(
        tmp_path / "permissions.sqlite3", "https://trace.example"
    )
    records: list[TraceRecord] = []

    def dispatch(record: TraceRecord, sender: object) -> bool:
        records.append(record)
        return True

    monkeypatch.setattr(manager, "dispatch", dispatch)
    sink = LangfuseTraceSink(
        manager,
        TraceDiagnosticChannel(),
        public_key="public",
        secret_key="secret",
    )
    sink.export(
        TraceRecord(
            operation_id="f" * 32,
            name="retrieval",
            status="success",
            duration_ms=1,
            model_id="C:/PRIVATE_PATH",
            steps=(
                TraceStep(
                    operation_id="f" * 32,
                    parent_id="f" * 32,
                    name="query-embedding",
                    status="success",
                    duration_ms=0,
                    model_id="test-model",
                    usage_details={"input_tokens": 2},
                ),
            ),
        )
    )
    assert records[0].model_id is None
    assert records[0].steps[0].model_id == "test-model"
