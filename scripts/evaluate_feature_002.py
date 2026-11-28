"""Run explicitly confirmed local-model observations for Feature 002 cases."""

import argparse
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.config import load_config
from app.embeddings import EmbeddingError, LocalEmbeddings
from app.evaluation import (
    EvaluationCase,
    load_evaluation_cases,
    validate_evaluation_cases,
)
from app.local_model import LocalModelError, OllamaRuntime, get_local_model
from app.question_workflow import AnswerOutcome, QuestionWorkflow
from app.retrieval import RetrievalError, new_operation_id, retrieve_versioned
from app.storage import SQLiteKnowledgeStore

_STATUSES = {"complete", "partial", "abstained", "no_knowledge", "failed"}
_POINT_STATUSES = {"pending", "covered", "not_covered", "unavailable"}
_SUPPORT_STATUSES = {
    "pending",
    "supported",
    "unsupported",
    "indeterminate",
    "unavailable",
}
_CITATION_STATUSES = {"pending", "correct", "incorrect", "unavailable"}
_ABSTENTION_STATUSES = {
    "pending",
    "appropriate",
    "inappropriate",
    "not_applicable",
    "unavailable",
}
_FAILURE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def build_observation(
    case: EvaluationCase,
    outcome: AnswerOutcome,
    *,
    elapsed_ms: int | None,
) -> dict[str, Any]:
    return {
        "case_id": case.id,
        "workflow_status": outcome.status,
        "expected_sources": list(case.expected_sources),
        "expected_point_reviews": [
            {"point": point["point"], "review_status": "pending"}
            for point in case.expected_answer_points
        ],
        "claims": [
            {
                "text": claim.text,
                "citations": [
                    {"filename": citation.filename, "chunk_id": citation.chunk_id}
                    for citation in claim.citations
                ],
                "support_review": "pending",
                "citation_review": "pending",
            }
            for claim in outcome.supported_claims
        ],
        "abstention_review": "pending",
        "missing_points_review": {"status": "pending", "points": None},
        "failure_code": outcome.error_code,
        "elapsed_ms": elapsed_ms,
    }


def validate_observation(observation: dict[str, Any]) -> None:
    required = {
        "case_id",
        "workflow_status",
        "expected_sources",
        "expected_point_reviews",
        "claims",
        "abstention_review",
        "missing_points_review",
        "failure_code",
        "elapsed_ms",
    }
    if set(observation) != required:
        raise ValueError("Evaluation observation has an invalid shape.")
    if (
        not isinstance(observation["case_id"], str)
        or not observation["case_id"]
        or not isinstance(observation["expected_sources"], list)
        or any(
            not isinstance(item, str) or not item
            for item in observation["expected_sources"]
        )
        or not isinstance(observation["expected_point_reviews"], list)
        or not isinstance(observation["claims"], list)
    ):
        raise ValueError("Evaluation observation has invalid case fields.")
    if (
        not isinstance(observation["workflow_status"], str)
        or observation["workflow_status"] not in _STATUSES
    ):
        raise ValueError("Evaluation observation has an invalid workflow status.")
    if (
        not isinstance(observation["abstention_review"], str)
        or observation["abstention_review"] not in _ABSTENTION_STATUSES
    ):
        raise ValueError("Evaluation observation has an invalid abstention review.")
    failure_code = observation["failure_code"]
    if failure_code is not None and (
        not isinstance(failure_code, str) or not _FAILURE_CODE.fullmatch(failure_code)
    ):
        raise ValueError("Evaluation observation has an unsafe failure code.")
    elapsed = observation["elapsed_ms"]
    if elapsed is not None and (
        isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed < 0
    ):
        raise ValueError("Evaluation observation has an invalid elapsed time.")
    for review in observation["expected_point_reviews"]:
        if (
            not isinstance(review, dict)
            or set(review) != {"point", "review_status"}
            or not isinstance(review["point"], str)
            or not review["point"].strip()
            or not isinstance(review["review_status"], str)
            or review["review_status"] not in _POINT_STATUSES
        ):
            raise ValueError("Evaluation observation has an invalid point review.")
    missing = observation["missing_points_review"]
    if (
        not isinstance(missing, dict)
        or set(missing) != {"status", "points"}
        or not isinstance(missing["status"], str)
        or missing["status"] not in {"pending", "reviewed", "unavailable"}
        or (
            missing["status"] in {"pending", "unavailable"}
            and missing["points"] is not None
        )
        or (
            missing["status"] == "reviewed"
            and (
                not isinstance(missing["points"], list)
                or any(not isinstance(point, str) for point in missing["points"])
            )
        )
    ):
        raise ValueError("Evaluation observation has invalid missing-point review.")
    for claim in observation["claims"]:
        if (
            not isinstance(claim, dict)
            or set(claim) != {"text", "citations", "support_review", "citation_review"}
            or not isinstance(claim.get("text"), str)
            or not isinstance(claim.get("citations"), list)
            or not isinstance(claim.get("support_review"), str)
            or claim["support_review"] not in _SUPPORT_STATUSES
            or not isinstance(claim.get("citation_review"), str)
            or claim["citation_review"] not in _CITATION_STATUSES
            or any(
                not isinstance(citation, dict)
                or set(citation) != {"filename", "chunk_id"}
                or not isinstance(citation["filename"], str)
                or not isinstance(citation["chunk_id"], str)
                for citation in claim["citations"]
            )
        ):
            raise ValueError("Evaluation observation has an invalid claim review.")


def _failure(code: str) -> AnswerOutcome:
    safe_code = code if _FAILURE_CODE.fullmatch(code) else "workflow_failed"
    return AnswerOutcome(status="failed", error_code=safe_code)


def run(dataset: Path, *, confirmed: bool) -> int:
    if not confirmed:
        raise ValueError("Pass --confirm-local-model to run local evaluation.")
    cases = load_evaluation_cases(dataset)
    validate_evaluation_cases(cases)
    try:
        config = load_config()
        embeddings = LocalEmbeddings(
            config.embedding_model, config.model_cache_dir, local_files_only=True
        )
        store = SQLiteKnowledgeStore(config.knowledge_dir / "knowledge.sqlite3")
        model = get_local_model(config)
    except EmbeddingError:
        _emit_unavailable_cases(cases, "provider_unavailable")
        return 0
    except (OSError, sqlite3.Error):
        _emit_unavailable_cases(cases, "storage_unavailable")
        return 0
    workflow = QuestionWorkflow(model)

    def evaluate_case(case: EvaluationCase) -> None:
        started = time.monotonic_ns()
        operation_id = new_operation_id()
        try:
            evidence = retrieve_versioned(
                store, embeddings, case.question, 5, operation_id
            )
            outcome = workflow.run(case.question, evidence)
        except RetrievalError as exc:
            outcome = _failure(exc.code)
        elapsed_ms = max(0, (time.monotonic_ns() - started) // 1_000_000)
        observation = build_observation(case, outcome, elapsed_ms=elapsed_ms)
        validate_observation(observation)
        print(json.dumps(observation, ensure_ascii=False))

    try:
        with OllamaRuntime(config.ollama_executable, config.ollama_host):
            for case in cases:
                evaluate_case(case)
    except LocalModelError as exc:
        _emit_unavailable_cases(cases, exc.code)
    return 0


def _emit_unavailable_cases(cases: list[EvaluationCase], code: str) -> None:
    for case in cases:
        observation = build_observation(
            case,
            _failure(code),
            elapsed_ms=None,
        )
        validate_observation(observation)
        print(json.dumps(observation, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluation/feature_002/cases.jsonl"),
    )
    parser.add_argument(
        "--confirm-local-model",
        action="store_true",
        help="confirm use of the manually prepared local answer model",
    )
    arguments = parser.parse_args()
    try:
        run(arguments.dataset, confirmed=arguments.confirm_local_model)
    except (OSError, ValueError, RetrievalError):
        parser.error(
            "The local evaluation could not run; check the dataset, local models, "
            "and knowledge index."
        )


if __name__ == "__main__":
    main()
