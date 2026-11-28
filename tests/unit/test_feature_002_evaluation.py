from pathlib import Path

import pytest

from app.evaluation import load_evaluation_cases, validate_evaluation_cases

_DATASET = Path(__file__).parents[2] / "evaluation" / "feature_002" / "cases.jsonl"


def test_bundled_dataset_has_required_case_types_and_sources() -> None:
    cases = load_evaluation_cases(_DATASET)

    validate_evaluation_cases(cases)
    assert len(cases) >= 5
    assert sum("answerable" in case.categories for case in cases) >= 3
    assert sum("unanswerable" in case.categories for case in cases) >= 1
    assert sum("multi_source" in case.categories for case in cases) >= 1
    assert all(case.expected_answer_points or case.no_support for case in cases)


def test_case_validation_rejects_invalid_multisource_points() -> None:
    cases = load_evaluation_cases(_DATASET)
    multi = next(case for case in cases if "multi_source" in case.categories)
    multi.expected_answer_points = [
        {"point": "one point", "source": "same.txt"},
        {"point": "another point", "source": "same.txt"},
    ]

    with pytest.raises(ValueError):
        validate_evaluation_cases(cases)
