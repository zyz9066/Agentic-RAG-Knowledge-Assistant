import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.embeddings import EmbeddingError
from app.evaluation import EvaluationCase
from app.question_workflow import AnswerOutcome, SupportedClaim
from scripts import evaluate_feature_002
from scripts.evaluate_feature_002 import (
    build_observation,
    run,
    validate_observation,
)

_DATASET = Path(__file__).parents[2] / "evaluation" / "feature_002" / "cases.jsonl"


def test_evaluator_requires_local_model_opt_in() -> None:
    with pytest.raises(ValueError, match="--confirm-local-model"):
        run(_DATASET, confirmed=False)


def test_evaluator_initializes_review_fields_as_pending() -> None:
    case = EvaluationCase(
        id="case-1",
        question="Question?",
        categories=("answerable",),
        expected_answer_points=[{"point": "A fact", "source": "facts.txt"}],
        expected_sources=("facts.txt",),
        no_support=False,
    )
    outcome = AnswerOutcome(
        status="complete",
        supported_claims=[
            SupportedClaim(
                text="A fact",
                citations=[],
            )
        ],
    )

    observation = build_observation(case, outcome, elapsed_ms=12)
    validate_observation(observation)

    assert observation["expected_point_reviews"][0]["review_status"] == "pending"
    assert observation["claims"][0]["support_review"] == "pending"
    assert observation["claims"][0]["citation_review"] == "pending"
    assert observation["abstention_review"] == "pending"
    assert observation["missing_points_review"] == {
        "status": "pending",
        "points": None,
    }
    assert observation["elapsed_ms"] == 12


def test_unmeasured_fields_remain_null_and_unavailable_is_distinct() -> None:
    case = EvaluationCase(
        id="case-2",
        question="Question?",
        categories=("unanswerable",),
        expected_answer_points=[],
        expected_sources=(),
        no_support=True,
    )
    outcome = AnswerOutcome(status="failed", error_code="local_model_unavailable")

    observation = build_observation(case, outcome, elapsed_ms=None)
    validate_observation(observation)
    observation["abstention_review"] = "unavailable"
    observation["missing_points_review"] = {
        "status": "unavailable",
        "points": None,
    }
    validate_observation(observation)


def test_missing_local_embedding_model_emits_safe_unavailable_observations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        evaluate_feature_002,
        "load_config",
        lambda: SimpleNamespace(
            embedding_model="local-model",
            model_cache_dir=tmp_path,
        ),
    )

    def missing_model(*_args: object, **_kwargs: object) -> None:
        raise EmbeddingError("private local cache path")

    monkeypatch.setattr(evaluate_feature_002, "LocalEmbeddings", missing_model)
    assert run(_DATASET, confirmed=True) == 0

    output = capsys.readouterr().out
    lines = output.splitlines()
    observations = [json.loads(line) for line in lines]
    assert len(observations) == 5
    assert {item["failure_code"] for item in observations} == {"provider_unavailable"}
    assert all(item["elapsed_ms"] is None for item in observations)
    assert "private local cache path" not in output
