import time

from app.question_jobs import QuestionJobRegistry
from app.question_workflow import AnswerOutcome


def _delayed_outcome(delay: float) -> AnswerOutcome:
    time.sleep(delay)
    return AnswerOutcome(status="complete")


def test_registry_rejects_overlap_and_correlates_results() -> None:
    registry = QuestionJobRegistry(worker_timeout=10)

    assert registry.submit("session", "request-1", _delayed_outcome, 0.3)
    assert not registry.submit("session", "request-2", _delayed_outcome, 0)
    assert registry.poll("session", "request-2") is None

    deadline = time.monotonic() + 10
    snapshot = registry.poll("session", "request-1")
    while snapshot is not None and snapshot.state == "running":
        assert time.monotonic() < deadline
        time.sleep(0.05)
        snapshot = registry.poll("session", "request-1")

    assert snapshot is not None
    assert snapshot.request_id == "request-1"
    assert snapshot.state == "complete"
    assert snapshot.outcome == AnswerOutcome(status="complete")


def test_worker_deadline_terminates_and_marks_failure() -> None:
    registry = QuestionJobRegistry(worker_timeout=0.1)

    assert registry.submit("session", "request", _delayed_outcome, 2)
    time.sleep(0.15)
    snapshot = registry.poll("session", "request")

    assert snapshot is not None
    assert snapshot.state == "failed"
    assert snapshot.outcome == AnswerOutcome(
        status="failed", error_code="worker_timeout"
    )
