"""Own one request-correlated, terminable worker per application session."""

import multiprocessing
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, Literal, Protocol

from app.config import AppConfig
from app.question_workflow import AnswerOutcome, Citation, QuestionWorkflow

JobState = Literal[
    "running", "complete", "partial", "abstained", "no_knowledge", "failed"
]
Worker = Callable[..., AnswerOutcome]


class _WorkerConnection(Protocol):
    def poll(self, timeout: float = 0.0) -> bool: ...

    def recv(self) -> Any: ...

    def close(self) -> None: ...


class _WorkerProcess(Protocol):
    def is_alive(self) -> bool: ...

    def terminate(self) -> None: ...

    def join(self, timeout: float | None = None) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class QuestionRequest:
    request_id: str
    question: str
    config: AppConfig
    evaluation_case_id: str | None = None
    evaluation_fields_confirmed: bool = False
    runtime_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    session_id: str
    request_id: str
    state: JobState
    outcome: AnswerOutcome | None


@dataclass(slots=True)
class _OwnedJob:
    session_id: str
    request_id: str
    process: _WorkerProcess | None
    connection: _WorkerConnection | None
    started_at: float
    state: JobState = "running"
    outcome: AnswerOutcome | None = None


def _freshen_outcome(store: Any, outcome: AnswerOutcome) -> AnswerOutcome:
    if not outcome.supported_claims:
        return outcome
    citations: list[Citation] = []
    for claim in outcome.supported_claims:
        for citation in claim.citations:
            if citation not in citations:
                citations.append(citation)
    try:
        from app.storage import CitationStamp

        current = store.citations_are_current(
            [
                CitationStamp(
                    document_id=citation.document_id,
                    filename=citation.filename,
                    chunk_id=citation.chunk_id,
                    revision=citation.revision,
                    digest=citation.digest,
                )
                for citation in citations
            ]
        )
    except (OSError, sqlite3.Error):
        return replace(
            outcome,
            status="failed",
            supported_claims=[],
            missing_explanation=None,
            error_code="storage_unavailable",
        )
    current_by_citation = dict(zip(citations, current))
    claims = [
        claim
        for claim in outcome.supported_claims
        if claim.citations
        and all(current_by_citation[item] for item in claim.citations)
    ]
    if len(claims) == len(outcome.supported_claims):
        return outcome
    if not claims:
        return replace(
            outcome,
            status="abstained",
            supported_claims=[],
            missing_explanation=(
                "A cited source changed. Submit the question again to retrieve "
                "current evidence."
            ),
            error_code=None,
        )
    return replace(
        outcome,
        status="partial",
        supported_claims=claims,
        missing_explanation=(
            "A cited source changed, so affected claims were removed. Submit the "
            "question again to retrieve current evidence."
        ),
    )


def run_question_request(request: QuestionRequest) -> AnswerOutcome:
    """Run retrieval and answer work inside the owned child process."""
    from app.embeddings import EmbeddingError, LocalEmbeddings
    from app.evaluation import (
        EvaluationSourceVerifier,
        load_evaluation_cases,
        validate_evaluation_cases,
    )
    from app.local_model import LocalModelError, get_local_model
    from app.observability import (
        EvaluationTracePayload,
        LangfuseTraceSink,
        TraceDiagnosticChannel,
        TracePermissionManager,
        WorkflowTracer,
    )
    from app.retrieval import RetrievalError, retrieve_versioned
    from app.storage import SQLiteKnowledgeStore

    config = request.config
    database = config.knowledge_dir / "knowledge.sqlite3"
    diagnostics = TraceDiagnosticChannel()
    tracer = WorkflowTracer(None, diagnostics)
    sink: LangfuseTraceSink | None = None
    try:
        if config.trace_host is not None:
            permissions = TracePermissionManager(database, config.trace_host)
            sink = LangfuseTraceSink(
                permissions,
                diagnostics,
                public_key=config.trace_public_key,
                secret_key=config.trace_secret_key,
            )
            tracer.set_sink(sink)
    except (OSError, sqlite3.Error, ValueError):
        diagnostics.record(request.request_id, "trace_unavailable")

    outcome = AnswerOutcome(status="failed", error_code="workflow_failed")
    with tracer.operation(
        request.request_id, "question", model_id=config.answer_model
    ) as operation:
        try:
            store = SQLiteKnowledgeStore(database)
            try:
                embeddings = LocalEmbeddings(
                    config.embedding_model,
                    config.model_cache_dir,
                    local_files_only=True,
                )
            except EmbeddingError:
                outcome = AnswerOutcome(
                    status="failed", error_code="provider_unavailable"
                )
                operation.set_status("failed")
                with operation.step("outcome"):
                    pass
                embeddings = None
            evaluation_case = None
            verifier: EvaluationSourceVerifier | None = None
            if embeddings is not None and request.evaluation_case_id:
                dataset = (
                    Path(__file__).parents[1]
                    / "evaluation"
                    / "feature_002"
                    / "cases.jsonl"
                )
                cases = load_evaluation_cases(dataset)
                validate_evaluation_cases(cases)
                evaluation_case = next(
                    (case for case in cases if case.id == request.evaluation_case_id),
                    None,
                )
                if evaluation_case is not None:
                    verifier = EvaluationSourceVerifier(
                        store,
                        embeddings,
                        cases,
                        dataset.parent / "sources",
                    )
                    if sink is not None:
                        sink.set_evaluation_eligibility(verifier.dispatch_eligibility)

            if embeddings is not None:
                with operation.step("retrieval", model_id=embeddings.model_id):
                    evidence = retrieve_versioned(
                        store,
                        embeddings,
                        request.question,
                        5,
                        request.request_id,
                    )
                if evidence:
                    if request.runtime_error_code is not None:
                        outcome = AnswerOutcome(
                            status="failed",
                            error_code=request.runtime_error_code,
                        )
                    else:
                        model = get_local_model(config)
                        model.validate_model()
                        outcome = QuestionWorkflow(model).run(
                            request.question, evidence, trace_operation=operation
                        )
                else:
                    outcome = AnswerOutcome(status="no_knowledge")
                with operation.step("freshness-check"):
                    outcome = _freshen_outcome(store, outcome)
                if (
                    evaluation_case is not None
                    and request.evaluation_fields_confirmed
                    and request.question == evaluation_case.question
                ):
                    source_ids = tuple(
                        dict.fromkeys(
                            (citation.filename, citation.chunk_id)
                            for claim in outcome.supported_claims
                            for citation in claim.citations
                        )
                    )
                    operation.set_evaluation_payload(
                        EvaluationTracePayload(
                            case_id=evaluation_case.id,
                            question=request.question,
                            source_ids=source_ids,
                            fields_confirmed=True,
                        )
                    )
                if outcome.status == "failed":
                    operation.set_status("failed")
                with operation.step("outcome"):
                    pass
        except RetrievalError as exc:
            outcome = AnswerOutcome(status="failed", error_code=exc.code)
            operation.set_status("failed")
            with operation.step("outcome"):
                pass
        except LocalModelError as exc:
            outcome = AnswerOutcome(status="failed", error_code=exc.code)
            operation.set_status("failed")
            with operation.step("outcome"):
                pass
        except (OSError, sqlite3.Error):
            outcome = AnswerOutcome(status="failed", error_code="storage_unavailable")
            operation.set_status("failed")
            with operation.step("outcome"):
                pass
    record = tracer.get_record(request.request_id)
    warnings = tuple(item.message for item in diagnostics.get(request.request_id))
    return AnswerOutcome(
        status=outcome.status,
        supported_claims=outcome.supported_claims,
        missing_explanation=outcome.missing_explanation,
        error_code=outcome.error_code,
        trace_record=record,
        trace_warnings=warnings,
    )


def _worker_entry(sender: Connection, target: Worker, args: tuple[Any, ...]) -> None:
    try:
        outcome = target(*args)
        if not isinstance(outcome, AnswerOutcome):
            outcome = AnswerOutcome(status="failed", error_code="workflow_failed")
    except Exception:  # noqa: BLE001 - worker failures become a safe terminal result.
        outcome = AnswerOutcome(status="failed", error_code="workflow_failed")
    try:
        sender.send(outcome)
    except (BrokenPipeError, EOFError, OSError):
        pass
    finally:
        sender.close()


class QuestionJobRegistry:
    """Atomically reject overlap and discard results from non-owning requests."""

    def __init__(self, *, worker_timeout: float = 300) -> None:
        if worker_timeout <= 0:
            raise ValueError("worker_timeout must be positive")
        self._worker_timeout = worker_timeout
        self._lock = threading.RLock()
        self._jobs: dict[str, _OwnedJob] = {}
        self._context = multiprocessing.get_context("spawn")

    def submit(
        self,
        session_id: str,
        request_id: str,
        target: Worker,
        *args: Any,
    ) -> bool:
        if not session_id or not request_id:
            raise ValueError("session_id and request_id are required")
        with self._lock:
            current = self._jobs.get(session_id)
            if current is not None and current.state == "running":
                self._collect(current)
                if current.state == "running":
                    return False
            receiver, sender = self._context.Pipe(duplex=False)
            process = self._context.Process(
                target=_worker_entry,
                args=(sender, target, args),
                daemon=True,
            )
            process.start()
            sender.close()
            self._jobs[session_id] = _OwnedJob(
                session_id=session_id,
                request_id=request_id,
                process=process,
                connection=receiver,
                started_at=time.monotonic(),
            )
            return True

    def poll(self, session_id: str, request_id: str) -> JobSnapshot | None:
        with self._lock:
            job = self._jobs.get(session_id)
            if job is None or job.request_id != request_id:
                return None
            self._collect(job)
            return JobSnapshot(job.session_id, job.request_id, job.state, job.outcome)

    def cancel(self, session_id: str, request_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(session_id)
            if job is None or job.request_id != request_id or job.state != "running":
                return False
            process = job.process
            if process is not None and process.is_alive():
                process.terminate()
                process.join(timeout=5)
            job.outcome = AnswerOutcome(status="failed", error_code="worker_timeout")
            job.state = "failed"
            self._close(job)
            return True

    def _collect(self, job: _OwnedJob) -> None:
        process, connection = job.process, job.connection
        if process is None or connection is None or job.state != "running":
            return
        if time.monotonic() - job.started_at >= self._worker_timeout:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            job.outcome = AnswerOutcome(status="failed", error_code="worker_timeout")
            job.state = "failed"
            self._close(job)
            return
        if connection.poll():
            try:
                outcome = connection.recv()
            except (EOFError, OSError):
                outcome = AnswerOutcome(status="failed", error_code="workflow_failed")
            if isinstance(outcome, AnswerOutcome):
                job.outcome = outcome
                job.state = outcome.status
            else:
                job.outcome = AnswerOutcome(
                    status="failed", error_code="workflow_failed"
                )
                job.state = "failed"
            process.join(timeout=1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            self._close(job)
            return
        if not process.is_alive():
            job.outcome = AnswerOutcome(status="failed", error_code="workflow_failed")
            job.state = "failed"
            self._close(job)

    @staticmethod
    def _close(job: _OwnedJob) -> None:
        if job.connection is not None:
            job.connection.close()
            job.connection = None
        if job.process is not None:
            job.process.close()
            job.process = None
