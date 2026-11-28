"""Privacy-first workflow tracing and destination permission enforcement."""

from __future__ import annotations

import ipaddress
import re
import socket
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

import httpx
from langfuse import Langfuse

OperationName = Literal["indexing", "retrieval", "question"]
OperationStatus = Literal["success", "failed", "rejected"]
StepStatus = Literal["success", "failed", "rejected"]
TraceExportStatus = Literal[
    "disabled", "unavailable", "failed", "unconfirmed", "confirmed"
]

_STEPS = {
    "indexing": {
        "validation",
        "reservation",
        "parsing",
        "chunking",
        "embedding",
        "storage",
    },
    "retrieval": {
        "input-validation",
        "query-embedding",
        "evidence-lookup-ranking",
    },
    "question": {
        "retrieval",
        "drafting",
        "verification",
        "freshness-check",
        "outcome",
    },
}
_MODEL_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?"
    r"(?:/[A-Za-z0-9][A-Za-z0-9._-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?)?"
    r"(?:@[A-Za-z0-9][A-Za-z0-9._-]*(?::[a-f0-9]{64})?)?$"
)
_DIAGNOSTIC_MESSAGES = {
    "trace_export_failed": "Trace export failed; the application result is unaffected.",
    "trace_disabled": "Trace export is disabled by the current permission settings.",
    "trace_unavailable": "Trace export is unavailable; the application result is unaffected.",
    "trace_unconfirmed": "Trace delivery could not be confirmed; the application result is unaffected.",
}


@dataclass(frozen=True, slots=True)
class TraceStep:
    operation_id: str
    parent_id: str
    name: str
    status: StepStatus
    duration_ms: int
    model_id: str | None = None
    usage_details: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TraceRecord:
    operation_id: str
    name: OperationName
    status: OperationStatus
    duration_ms: int
    model_id: str | None
    steps: tuple[TraceStep, ...]
    evaluation_payload: EvaluationTracePayload | None = None
    export_status: TraceExportStatus = "unconfirmed"


@dataclass(frozen=True, slots=True)
class EvaluationTracePayload:
    case_id: str
    question: str
    source_ids: tuple[tuple[str, str], ...]
    fields_confirmed: bool


@dataclass(frozen=True, slots=True)
class TraceDiagnostic:
    operation_id: str
    code: str
    message: str


class TraceSink(Protocol):
    def export(self, record: TraceRecord) -> TraceExportStatus: ...


class TraceDiagnosticChannel:
    """Provide safe, operation-correlated trace warnings."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, list[TraceDiagnostic]] = {}

    def record(self, operation_id: str, code: str) -> None:
        message = _DIAGNOSTIC_MESSAGES[code]
        with self._lock:
            self._items.setdefault(operation_id, []).append(
                TraceDiagnostic(operation_id, code, message)
            )

    def get(self, operation_id: str) -> tuple[TraceDiagnostic, ...]:
        with self._lock:
            return tuple(self._items.get(operation_id, ()))


class RecordingTraceSink:
    """Deterministic offline trace sink for tests."""

    def __init__(self) -> None:
        self.records: list[TraceRecord] = []

    def export(self, record: TraceRecord) -> TraceExportStatus:
        self.records.append(record)
        return "confirmed"


def _safe_model_id(value: str | None) -> str | None:
    if value is None:
        return None
    return value if _MODEL_ID.fullmatch(value) else None


def _safe_usage(values: Mapping[str, int]) -> dict[str, int]:
    allowed = {"input_tokens", "output_tokens", "total_tokens"}
    return {
        key: value
        for key, value in values.items()
        if key in allowed
        and isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    }


def _sanitize_record(record: TraceRecord) -> TraceRecord:
    if (
        re.fullmatch(r"[a-f0-9]{32}", record.operation_id) is None
        or record.name not in _STEPS
        or record.status not in {"success", "failed", "rejected"}
        or not isinstance(record.duration_ms, int)
        or record.duration_ms < 0
    ):
        raise ValueError("Invalid trace record.")
    steps: list[TraceStep] = []
    for step in record.steps:
        if (
            step.operation_id != record.operation_id
            or step.parent_id != record.operation_id
            or step.name not in _STEPS[record.name]
            or step.status not in {"success", "failed", "rejected"}
            or not isinstance(step.duration_ms, int)
            or step.duration_ms < 0
        ):
            raise ValueError("Invalid trace step.")
        steps.append(
            TraceStep(
                operation_id=record.operation_id,
                parent_id=record.operation_id,
                name=step.name,
                status=step.status,
                duration_ms=step.duration_ms,
                model_id=_safe_model_id(step.model_id),
                usage_details=_safe_usage(step.usage_details),
            )
        )
    payload = record.evaluation_payload
    if payload is not None:
        if (
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", payload.case_id) is None
            or not payload.fields_confirmed
            or not isinstance(payload.question, str)
            or not payload.question.strip()
            or any(
                not filename or not chunk_id
                for filename, chunk_id in payload.source_ids
            )
        ):
            raise ValueError("Invalid evaluation trace payload.")
        payload = EvaluationTracePayload(
            case_id=payload.case_id,
            question=payload.question,
            source_ids=tuple(payload.source_ids),
            fields_confirmed=True,
        )
    return TraceRecord(
        operation_id=record.operation_id,
        name=record.name,
        status=record.status,
        duration_ms=record.duration_ms,
        model_id=_safe_model_id(record.model_id),
        steps=tuple(steps),
        evaluation_payload=payload,
        export_status=record.export_status,
    )


class TraceOperation:
    def __init__(self, operation_id: str, name: OperationName) -> None:
        self.operation_id = operation_id
        self.name = name
        self.status: OperationStatus = "success"
        self.steps: list[TraceStep] = []
        self.model_id: str | None = None
        self.evaluation_payload: EvaluationTracePayload | None = None

    def set_model(self, model_id: str | None) -> None:
        self.model_id = _safe_model_id(model_id)

    def set_status(self, status: OperationStatus) -> None:
        self.status = status

    def set_evaluation_payload(self, payload: EvaluationTracePayload | None) -> None:
        self.evaluation_payload = payload

    @contextmanager
    def step(
        self,
        name: str,
        *,
        model_id: str | None = None,
        usage_details: Mapping[str, int] | None = None,
    ) -> Iterator[None]:
        if name not in _STEPS[self.name]:
            raise ValueError("Unknown trace step.")
        started = time.monotonic_ns()
        status: StepStatus = "success"
        try:
            yield
        except Exception:
            status = "failed"
            self.status = "failed"
            raise
        finally:
            self.steps.append(
                TraceStep(
                    operation_id=self.operation_id,
                    parent_id=self.operation_id,
                    name=name,
                    status=status,
                    duration_ms=max(0, (time.monotonic_ns() - started) // 1_000_000),
                    model_id=_safe_model_id(model_id),
                    usage_details=_safe_usage(usage_details or {}),
                )
            )


class WorkflowTracer:
    """Build allowlisted trace data and isolate exporter errors from core work."""

    def __init__(
        self, sink: TraceSink | None, diagnostics: TraceDiagnosticChannel
    ) -> None:
        self._sink = sink
        self._diagnostics = diagnostics
        self._record_lock = threading.Lock()
        self._records: dict[str, TraceRecord] = {}

    @property
    def diagnostics(self) -> TraceDiagnosticChannel:
        return self._diagnostics

    def set_sink(self, sink: TraceSink | None) -> None:
        self._sink = sink

    def get_record(self, operation_id: str) -> TraceRecord | None:
        with self._record_lock:
            return self._records.get(operation_id)

    @contextmanager
    def operation(
        self,
        operation_id: str,
        name: OperationName,
        *,
        model_id: str | None = None,
    ) -> Iterator[TraceOperation]:
        operation = TraceOperation(operation_id, name)
        operation.set_model(model_id)
        started = time.monotonic_ns()
        try:
            yield operation
        except Exception:
            operation.set_status("failed")
            raise
        finally:
            valid_id = re.fullmatch(r"[a-f0-9]{32}", operation_id) is not None
            if self._sink is None and valid_id:
                self._diagnostics.record(operation_id, "trace_unavailable")
            if valid_id:
                record = TraceRecord(
                    operation_id=operation_id,
                    name=name,
                    status=operation.status,
                    duration_ms=max(0, (time.monotonic_ns() - started) // 1_000_000),
                    model_id=operation.model_id,
                    steps=tuple(operation.steps),
                    evaluation_payload=operation.evaluation_payload,
                )
                export_status: TraceExportStatus = "unavailable"
                if self._sink is not None:
                    export_status = "unconfirmed"
                    try:
                        result = self._sink.export(record)
                        if result in {
                            "disabled",
                            "unavailable",
                            "failed",
                            "unconfirmed",
                            "confirmed",
                        }:
                            export_status = result
                        if result == "unconfirmed" and not self._diagnostics.get(
                            operation_id
                        ):
                            self._diagnostics.record(operation_id, "trace_unconfirmed")
                    except Exception:  # noqa: BLE001 - export errors never alter core work.
                        export_status = "failed"
                        if not self._diagnostics.get(operation_id):
                            self._diagnostics.record(
                                operation_id, "trace_export_failed"
                            )
                with self._record_lock:
                    self._records[operation_id] = replace(
                        record, export_status=export_status
                    )


class TracePermissionManager:
    """Persist external opt-in and serialize permission changes with dispatch."""

    def __init__(self, database: Path, destination: str) -> None:
        parsed = urlsplit(destination.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Trace destination must be an HTTP(S) URL without credentials."
            )
        self.database = database
        self.destination = destination.strip().rstrip("/")
        self._parsed = urlsplit(self.destination)
        self._process_id = object()
        self._local_confirmation: tuple[object, int] | None = None
        database.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trace_permissions (
                    destination TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS trace_route_epochs (
                    destination TEXT PRIMARY KEY,
                    epoch INTEGER NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database, timeout=30)

    @property
    def _local_ip(self) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        try:
            address = ipaddress.ip_address(self._parsed.hostname or "")
        except ValueError:
            return None
        return address if address.is_loopback else None

    @property
    def state(self) -> str:
        if self._local_ip is not None:
            return (
                "local_confirmed" if self._local_is_confirmed() else "local_unconfirmed"
            )
        with closing(self._connect()) as connection:
            granted = connection.execute(
                "SELECT 1 FROM trace_permissions WHERE destination = ?",
                (self.destination,),
            ).fetchone()
        return "external_enabled" if granted else "external_disabled"

    def _route_epoch(self, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT epoch FROM trace_route_epochs WHERE destination = ?",
            (self.destination,),
        ).fetchone()
        return int(row[0]) if row else 0

    def _local_is_confirmed(self) -> bool:
        if self._local_confirmation is None:
            return False
        with closing(self._connect()) as connection:
            epoch = self._route_epoch(connection)
        process, confirmed_epoch = self._local_confirmation
        return process is self._process_id and confirmed_epoch == epoch

    def _check_loopback_peer(self) -> bool:
        address = self._local_ip
        if address is None:
            return False
        port = self._parsed.port or (443 if self._parsed.scheme == "https" else 80)
        try:
            with socket.create_connection(
                (str(address), port), timeout=1
            ) as connection:
                peer = ipaddress.ip_address(connection.getpeername()[0])
                return peer.is_loopback and peer == address
        except (OSError, ValueError):
            return False

    def confirm_local(self, *, attested: bool) -> bool:
        """Record process-lifetime confirmation only after direct peer validation."""
        if not attested or self._local_ip is None or not self._check_loopback_peer():
            return False
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            epoch = self._route_epoch(connection)
            connection.commit()
        self._local_confirmation = (self._process_id, epoch)
        return True

    def grant_external(self) -> None:
        if self._local_ip is not None:
            raise ValueError(
                "Loopback destinations use process-lifetime local confirmation."
            )
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO trace_permissions VALUES (?)",
                (self.destination,),
            )
            connection.commit()

    def revoke(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM trace_permissions WHERE destination = ?",
                (self.destination,),
            )
            connection.execute(
                """
                INSERT INTO trace_route_epochs VALUES (?, 1)
                ON CONFLICT(destination) DO UPDATE SET epoch = epoch + 1
                """,
                (self.destination,),
            )
            connection.commit()
        self._local_confirmation = None

    def invalidate_route(self) -> None:
        """Invalidate local confirmations across processes sharing this database."""
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO trace_route_epochs VALUES (?, 1)
                ON CONFLICT(destination) DO UPDATE SET epoch = epoch + 1
                """,
                (self.destination,),
            )
            connection.commit()
        self._local_confirmation = None

    def create_httpx_client(self) -> httpx.Client:
        return httpx.Client(timeout=5, trust_env=False, follow_redirects=False)

    def dispatch(
        self,
        record: TraceRecord,
        sender: Callable[[TraceRecord, str], None],
        *,
        evaluation_eligibility: (Callable[[EvaluationTracePayload], Any] | None) = None,
    ) -> bool:
        """Authorize and synchronously flush a trace while revocation is excluded."""
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._local_ip is not None:
                allowed = self._local_is_confirmed() and self._check_loopback_peer()
            else:
                allowed = (
                    connection.execute(
                        "SELECT 1 FROM trace_permissions WHERE destination = ?",
                        (self.destination,),
                    ).fetchone()
                    is not None
                )
            try:
                payload = record.evaluation_payload
                if payload is None:
                    if not allowed:
                        connection.commit()
                        return False
                    sender(record, self.destination)
                else:
                    if (
                        not allowed
                        or not payload.fields_confirmed
                        or evaluation_eligibility is None
                    ):
                        connection.commit()
                        return False
                    with evaluation_eligibility(payload) as eligible:
                        if not eligible:
                            connection.commit()
                            return False
                        sender(record, self.destination)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            return True


class LangfuseTraceSink:
    """Create and flush only allowlisted records after permission is verified."""

    def __init__(
        self,
        permissions: TracePermissionManager,
        diagnostics: TraceDiagnosticChannel,
        *,
        public_key: str | None,
        secret_key: str | None,
        evaluation_eligibility: (Callable[[EvaluationTracePayload], Any] | None) = None,
    ) -> None:
        self._permissions = permissions
        self._diagnostics = diagnostics
        self._public_key = public_key
        self._secret_key = secret_key
        self._evaluation_eligibility = evaluation_eligibility

    def set_evaluation_eligibility(
        self, eligibility: Callable[[EvaluationTracePayload], Any] | None
    ) -> None:
        self._evaluation_eligibility = eligibility

    def export(self, record: TraceRecord) -> TraceExportStatus:
        if not self._public_key or not self._secret_key:
            self._diagnostics.record(record.operation_id, "trace_unavailable")
            return "unavailable"
        try:
            sanitized = _sanitize_record(record)
            if sanitized.evaluation_payload is None:
                sent = self._permissions.dispatch(sanitized, self._send)
            else:
                sent = self._permissions.dispatch(
                    sanitized,
                    self._send,
                    evaluation_eligibility=self._evaluation_eligibility,
                )
        except Exception:  # noqa: BLE001 - export failures are surfaced separately.
            self._diagnostics.record(record.operation_id, "trace_export_failed")
            return "failed"
        else:
            if not sent:
                self._diagnostics.record(record.operation_id, "trace_disabled")
                return "disabled"
            self._diagnostics.record(record.operation_id, "trace_unconfirmed")
            return "unconfirmed"

    def _send(self, record: TraceRecord, destination: str) -> None:
        transport = self._permissions.create_httpx_client()
        client = Langfuse(
            public_key=self._public_key,
            secret_key=self._secret_key,
            host=destination,
            httpx_client=transport,
            tracing_enabled=True,
            flush_at=1,
            flush_interval=1,
        )
        try:
            with client.start_as_current_observation(
                as_type="chain",
                name=record.name,
                input={
                    "operation_id": record.operation_id,
                    **(
                        {
                            "evaluation": {
                                "question": record.evaluation_payload.question,
                                "source_ids": [
                                    {"filename": filename, "chunk_id": chunk_id}
                                    for filename, chunk_id in record.evaluation_payload.source_ids
                                ],
                            }
                        }
                        if record.evaluation_payload is not None
                        else {}
                    ),
                },
                level="ERROR" if record.status == "failed" else "DEFAULT",
                metadata={"duration_ms": record.duration_ms},
            ) as root:
                for step in record.steps:
                    with client.start_as_current_observation(
                        as_type="span",
                        name=step.name,
                        level="ERROR" if step.status == "failed" else "DEFAULT",
                        metadata={
                            "duration_ms": step.duration_ms,
                            "status": step.status,
                            **(
                                {"model_id": step.model_id}
                                if step.model_id is not None
                                else {}
                            ),
                            **(
                                {"usage_details": dict(step.usage_details)}
                                if step.usage_details
                                else {}
                            ),
                        },
                    ):
                        pass
                root.update(
                    output={"status": record.status},
                    metadata=(
                        {"model_id": record.model_id}
                        if record.model_id is not None
                        else {}
                    ),
                )
            client.flush()
        finally:
            client.shutdown()
            transport.close()
