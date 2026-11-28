"""Evaluation-case loading and dispatch-time sample-source verification."""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePath

from app.embeddings import EmbeddingProvider
from app.ingestion import UploadEntry, chunk_pages, extract_pages
from app.observability import EvaluationTracePayload
from app.storage import SQLiteKnowledgeStore

_CATEGORIES = {"answerable", "unanswerable", "multi_source"}


@dataclass(slots=True)
class EvaluationCase:
    id: str
    question: str
    categories: tuple[str, ...]
    expected_answer_points: list[dict[str, str]]
    expected_sources: tuple[str, ...]
    no_support: bool


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError("The evaluation dataset could not be read.") from exc
    for line in lines:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            cases.append(
                EvaluationCase(
                    id=data["id"],
                    question=data["question"],
                    categories=tuple(data["categories"]),
                    expected_answer_points=list(data["expected_answer_points"]),
                    expected_sources=tuple(data["expected_sources"]),
                    no_support=data["no_support"],
                )
            )
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "The evaluation dataset contains an invalid case."
            ) from exc
    return cases


def validate_evaluation_cases(cases: list[EvaluationCase]) -> None:
    if len(cases) < 5 or len({case.id for case in cases}) != len(cases):
        raise ValueError("The evaluation corpus needs five unique cases.")
    if (
        sum("answerable" in case.categories for case in cases) < 3
        or not any("unanswerable" in case.categories for case in cases)
        or not any("multi_source" in case.categories for case in cases)
    ):
        raise ValueError("The evaluation corpus is missing a required case type.")
    for case in cases:
        if (
            re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", case.id) is None
            or not case.question.strip()
            or not case.categories
            or set(case.categories) - _CATEGORIES
            or len(set(case.expected_sources)) != len(case.expected_sources)
            or any(
                not isinstance(source, str)
                or PurePath(source).name != source
                or "/" in source
                or "\\" in source
                or not source.endswith(".txt")
                for source in case.expected_sources
            )
        ):
            raise ValueError("An evaluation case is malformed.")
        if case.no_support:
            if (
                "unanswerable" not in case.categories
                or case.expected_sources
                or case.expected_answer_points
            ):
                raise ValueError("A no-support case must have no expected sources.")
        elif not case.expected_sources or not case.expected_answer_points:
            raise ValueError("Answerable cases need points and sources.")
        for point in case.expected_answer_points:
            if (
                not isinstance(point, dict)
                or not isinstance(point.get("point"), str)
                or not point["point"].strip()
                or point.get("source") not in case.expected_sources
            ):
                raise ValueError("An expected answer point has an invalid source.")
        if "multi_source" in case.categories:
            points = case.expected_answer_points
            if (
                len(points) < 2
                or len({point["point"] for point in points}) < 2
                or len({point["source"] for point in points}) < 2
            ):
                raise ValueError(
                    "Multi-source points must be directly supported by separate sources."
                )


class EvaluationSourceVerifier:
    """Keep contentful trace fields eligible only for exact bundled sources."""

    def __init__(
        self,
        store: SQLiteKnowledgeStore,
        provider: EmbeddingProvider,
        cases: list[EvaluationCase],
        source_dir: Path,
    ) -> None:
        self._store = store
        self._provider = provider
        validate_evaluation_cases(cases)
        self._cases = {case.id: case for case in cases}
        self._source_dir = source_dir.resolve()

    def _expected_chunks(self, filename: str) -> list[tuple[str, str, int | None]]:
        path = (self._source_dir / filename).resolve()
        if not path.is_relative_to(self._source_dir):
            return []
        try:
            data = path.read_bytes()
        except OSError:
            return []
        pages = extract_pages(UploadEntry(filename, data))
        chunks = chunk_pages(
            pages, self._provider.token_count, self._provider.max_tokens
        )
        return [
            (str(index), chunk.text, chunk.page) for index, chunk in enumerate(chunks)
        ]

    @contextmanager
    def dispatch_eligibility(self, payload: EvaluationTracePayload) -> Iterator[bool]:
        case = self._cases.get(payload.case_id)
        is_valid = (
            case is not None
            and payload.fields_confirmed
            and payload.question == case.question
            and len(set(payload.source_ids)) == len(payload.source_ids)
        )
        with self._store.read_snapshot() as connection:
            if is_valid and case is not None:
                allowed_sources = set(case.expected_sources)
                is_valid = all(
                    filename in allowed_sources for filename, _ in payload.source_ids
                )
                if is_valid:
                    for filename in case.expected_sources:
                        expected = self._expected_chunks(filename)
                        rows = connection.execute(
                            """
                            SELECT documents.embedding_model_id,
                                   documents.embedding_dimension,
                                   chunks.chunk_id, chunks.text, chunks.page
                            FROM documents
                            JOIN chunks USING (document_id)
                            WHERE documents.filename = ?
                            ORDER BY chunks.position
                            """,
                            (filename,),
                        ).fetchall()
                        actual = [(row[2], row[3], row[4]) for row in rows]
                        is_valid = (
                            bool(expected)
                            and actual == expected
                            and all(
                                row[0] == self._provider.model_id
                                and row[1] == self._provider.dimension
                                for row in rows
                            )
                        )
                eligible_ids = {
                    (filename, chunk_id)
                    for filename in case.expected_sources
                    for chunk_id, _, _ in self._expected_chunks(filename)
                }
                is_valid = is_valid and set(payload.source_ids) <= eligible_ids
            yield bool(is_valid)
