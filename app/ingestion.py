"""Validation and processing of submitted knowledge documents."""

import logging
import sqlite3
from collections import Counter
from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack, nullcontext
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from typing import Literal
from uuid import uuid4

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.embeddings import EmbeddingError, EmbeddingProvider
from app.observability import TraceOperation, WorkflowTracer
from app.storage import Chunk, ReservationConflict, SQLiteKnowledgeStore

MAX_FILES = 10
MAX_FILE_BYTES = 10 * 1024 * 1024
_REJECTION_MESSAGES = {
    "count": "a batch may contain at most 10 files",
    "duplicate": "duplicate filename in this batch",
    "empty": "the file is empty or contains no text",
    "type": "supported file types are .txt and .pdf",
    "size": "the file exceeds 10 MiB",
    "encoding": "text files must be valid UTF-8",
    "encrypted": "encrypted PDFs are not supported",
}

# Parser warnings can include document bytes; callers report safe failure categories.
_pdf_logger = logging.getLogger("pypdf")
_pdf_logger.addHandler(logging.NullHandler())
_pdf_logger.propagate = False


@dataclass(frozen=True, slots=True)
class UploadEntry:
    filename: str
    data: bytes


@dataclass(frozen=True, slots=True)
class ValidationResult:
    operation_id: str
    filename: str
    status: Literal["validating", "rejected"]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UploadBatch:
    batch_id: str
    entries: tuple[UploadEntry, ...]
    operation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IndexingConsent:
    batch_id: str
    provider_id: str
    data_description: str


@dataclass(frozen=True, slots=True)
class UploadResult:
    operation_id: str
    filename: str
    status: Literal[
        "pending", "validating", "processing", "indexed", "failed", "rejected"
    ]
    message: str
    reasons: tuple[str, ...] = ()


def new_upload_batch(entries: list[UploadEntry]) -> UploadBatch:
    """Snapshot submitted entries and assign identifiers before validation."""
    return UploadBatch(uuid4().hex, tuple(entries), tuple(uuid4().hex for _ in entries))


def grant_indexing_consent(
    batch: UploadBatch, provider: EmbeddingProvider
) -> IndexingConsent:
    """Bind explicit caller authorization to one batch and provider identity."""
    return IndexingConsent(
        batch.batch_id, provider.provider_id, provider.data_description
    )


def describe_provider(provider: EmbeddingProvider) -> str:
    """Provide the service and data disclosure for the caller to display."""
    if not provider.provider_id.strip() or not provider.data_description.strip():
        raise ValueError("The provider disclosure is unavailable.")
    return f"{provider.provider_id}: {provider.data_description}"


class ContentError(ValueError):
    """Content cannot be safely extracted or split."""


class _ConsentRequired(Exception):
    pass


class _ProviderUnavailable(Exception):
    pass


_PDF_PARSE_ERRORS = (
    PyPdfError,
    EOFError,
    ValueError,
    TypeError,
    IndexError,
    KeyError,
    OverflowError,
)


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    text: str
    page: int | None


def extract_pages(entry: UploadEntry) -> list[ExtractedPage]:
    """Extract text and one-based PDF page provenance."""
    extension = PurePath(entry.filename).suffix.lower()
    if extension == ".txt":
        try:
            text = entry.data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ContentError("Text must be UTF-8 encoded.") from None
        if not text.strip():
            raise ContentError("The file contains no extractable text.")
        return [ExtractedPage(text, None)]
    if extension != ".pdf":
        raise ContentError("Unsupported file type.")

    try:
        reader = PdfReader(BytesIO(entry.data))
        if reader.is_encrypted:
            raise ContentError("Encrypted PDFs are not supported.")
        pages = [
            ExtractedPage(text, page_number)
            for page_number, page in enumerate(reader.pages, start=1)
            if (text := page.extract_text()).strip()
        ]
    except ContentError:
        raise
    except _PDF_PARSE_ERRORS as exc:
        raise ContentError("The PDF could not be read.") from exc
    if not pages:
        raise ContentError("The PDF contains no extractable text.")
    return pages


def chunk_pages(
    pages: list[ExtractedPage], token_count: Callable[[str], int], max_tokens: int
) -> list[ExtractedPage]:
    """Split pages with overlap, retaining text and accounting for special tokens."""
    if max_tokens <= 0:
        raise ContentError("The embedding model has an invalid token limit.")
    chunks: list[ExtractedPage] = []
    for page in pages:
        start = 0
        while start < len(page.text):
            low, high = 0, 1
            remaining = len(page.text) - start
            while (
                high <= remaining
                and token_count(page.text[start : start + high]) <= max_tokens
            ):
                low, high = high, high * 2
            high = min(high, remaining)
            while low < high:
                mid = (low + high + 1) // 2
                if token_count(page.text[start : start + mid]) <= max_tokens:
                    low = mid
                else:
                    high = mid - 1
            if low == 0:
                raise ContentError(
                    "Text cannot fit within the embedding model's token limit."
                )
            text = page.text[start : start + low]
            chunks.append(ExtractedPage(text, page.page))
            if start + low == len(page.text):
                break
            start += max(1, low - low // 5)
    if not chunks:
        raise ContentError("The file contains no extractable text.")
    return chunks


def validate_batch(entries: list[UploadEntry]) -> list[ValidationResult]:
    """Validate a snapshot without disclosing file contents in errors."""
    return _validate_snapshot(new_upload_batch(entries))


def _validate_snapshot(batch: UploadBatch) -> list[ValidationResult]:
    entries, identifiers = batch.entries, batch.operation_ids
    if len(entries) > MAX_FILES:
        return [
            ValidationResult(operation_id, entry.filename, "rejected", ("count",))
            for operation_id, entry in zip(identifiers, entries)
        ]

    counts = Counter(entry.filename for entry in entries)
    return [
        _validate_entry(entry, operation_id, counts[entry.filename] > 1)
        for operation_id, entry in zip(identifiers, entries)
    ]


def _validate_entry(
    entry: UploadEntry, operation_id: str, duplicate: bool
) -> ValidationResult:
    reasons: list[str] = []
    extension = PurePath(entry.filename).suffix.lower()
    if duplicate:
        reasons.append("duplicate")
    if not entry.data:
        reasons.append("empty")
    if extension not in {".txt", ".pdf"}:
        reasons.append("type")
    if len(entry.data) > MAX_FILE_BYTES:
        reasons.append("size")

    if not reasons and extension == ".txt":
        try:
            text = entry.data.decode("utf-8-sig")
        except UnicodeDecodeError:
            reasons.append("encoding")
        else:
            if not text.strip():
                reasons.append("empty")
    elif not reasons and extension == ".pdf":
        try:
            encrypted = PdfReader(BytesIO(entry.data)).is_encrypted
        except _PDF_PARSE_ERRORS:
            # Parsing errors are reported as processing failures, not rejections.
            pass
        else:
            if encrypted:
                reasons.append("encrypted")
    return ValidationResult(
        operation_id=operation_id,
        filename=entry.filename,
        status="rejected" if reasons else "validating",
        reasons=tuple(reasons),
    )


def process_batch(
    batch: UploadBatch,
    store: SQLiteKnowledgeStore,
    provider: EmbeddingProvider | None,
    *,
    consent: IndexingConsent | None = None,
    on_status: Callable[[UploadResult], None] | None = None,
    tracer: WorkflowTracer | None = None,
    provider_factory: Callable[[], EmbeddingProvider] | None = None,
) -> list[UploadResult]:
    """Index each submitted entry independently and report safe outcomes."""
    results: list[UploadResult] = []

    def report(result: UploadResult) -> None:
        if on_status is not None:
            on_status(result)

    resolved_provider = provider
    provider_resolved = provider is not None or provider_factory is None

    def get_provider() -> EmbeddingProvider | None:
        nonlocal resolved_provider, provider_resolved
        if not provider_resolved and provider_factory is not None:
            provider_resolved = True
            try:
                resolved_provider = provider_factory()
            except EmbeddingError:
                resolved_provider = None
        return resolved_provider

    for operation_id, entry in zip(batch.operation_ids, batch.entries):
        report(
            UploadResult(
                operation_id, entry.filename, "pending", "Waiting to validate."
            )
        )
    over_limit = len(batch.entries) > MAX_FILES
    duplicate_counts = Counter(entry.filename for entry in batch.entries)
    for operation_id, entry in zip(batch.operation_ids, batch.entries):
        context = (
            tracer.operation(
                operation_id,
                "indexing",
                model_id=resolved_provider.model_id
                if resolved_provider is not None
                else None,
            )
            if tracer is not None
            else nullcontext(None)
        )
        with context as operation:

            def step(name: str):
                return operation.step(name) if operation is not None else nullcontext()

            if over_limit:
                with step("validation"):
                    validation = ValidationResult(
                        operation_id, entry.filename, "rejected", ("count",)
                    )
                if operation is not None:
                    operation.set_status("rejected")
                result = _validation_failure(validation)
            else:
                report(
                    UploadResult(
                        operation_id, entry.filename, "validating", "Validating file."
                    )
                )
                with step("validation"):
                    validation = _validate_entry(
                        entry, operation_id, duplicate_counts[entry.filename] > 1
                    )
                if validation.status == "rejected":
                    if operation is not None:
                        operation.set_status("rejected")
                    result = _validation_failure(validation)
                else:
                    result = _process_validated_entry(
                        batch,
                        entry,
                        operation_id,
                        store,
                        get_provider,
                        consent,
                        operation,
                        step,
                        report,
                    )
                    if operation is not None:
                        operation.set_status(
                            "success"
                            if result.status == "indexed"
                            else "rejected"
                            if result.status == "rejected"
                            else "failed"
                        )
            report(result)
            results.append(result)
    return results


def _validation_failure(validation: ValidationResult) -> UploadResult:
    return UploadResult(
        validation.operation_id,
        validation.filename,
        "rejected",
        "File rejected: "
        + "; ".join(_REJECTION_MESSAGES[reason] for reason in validation.reasons)
        + ".",
        validation.reasons,
    )


def _process_validated_entry(
    batch: UploadBatch,
    entry: UploadEntry,
    operation_id: str,
    store: SQLiteKnowledgeStore,
    get_provider: Callable[[], EmbeddingProvider | None],
    consent: IndexingConsent | None,
    operation: TraceOperation | None,
    step: Callable[[str], AbstractContextManager[None]],
    report: Callable[[UploadResult], None],
) -> UploadResult:
    try:
        with ExitStack() as reservation:
            with step("reservation"):
                reservation.enter_context(store.reserve(entry.filename))
            report(
                UploadResult(
                    operation_id, entry.filename, "processing", "Indexing file."
                )
            )
            provider = get_provider()
            if provider is None:
                raise _ProviderUnavailable
            if operation is not None:
                operation.set_model(provider.model_id)
            if provider.sends_text_externally and (
                not provider.provider_id.strip()
                or not provider.data_description.strip()
            ):
                raise _ProviderUnavailable
            if provider.sends_text_externally and consent != IndexingConsent(
                batch.batch_id, provider.provider_id, provider.data_description
            ):
                raise _ConsentRequired
            with step("parsing"):
                pages = extract_pages(entry)
            with step("chunking"):
                pieces = chunk_pages(pages, provider.token_count, provider.max_tokens)
            with step("embedding"):
                vectors = provider.embed([piece.text for piece in pieces])
                if len(vectors) != len(pieces):
                    raise EmbeddingError(
                        "The embedding provider returned an invalid result."
                    )
            chunks = [
                Chunk(str(index), piece.text, tuple(vector), piece.page)
                for index, (piece, vector) in enumerate(zip(pieces, vectors))
            ]
            with step("storage"):
                store.replace(entry.filename, provider.model_id, chunks)
    except ReservationConflict:
        if operation is not None:
            operation.set_status("rejected")
        return UploadResult(
            operation_id,
            entry.filename,
            "rejected",
            "File is being indexed; retry later.",
        )
    except _ConsentRequired:
        return UploadResult(
            operation_id,
            entry.filename,
            "failed",
            "External indexing requires consent for this batch and provider.",
        )
    except _ProviderUnavailable:
        return UploadResult(
            operation_id,
            entry.filename,
            "failed",
            "The embedding provider is unavailable.",
        )
    except ContentError:
        return UploadResult(
            operation_id,
            entry.filename,
            "failed",
            "The file could not be read or has no extractable text; check its content.",
        )
    except EmbeddingError:
        return UploadResult(
            operation_id,
            entry.filename,
            "failed",
            "The embedding provider could not process the file; check its configuration.",
        )
    except (sqlite3.Error, OSError, RuntimeError, ValueError):
        return UploadResult(
            operation_id, entry.filename, "failed", "Indexing failed; please retry."
        )
    return UploadResult(operation_id, entry.filename, "indexed", "File indexed.")
