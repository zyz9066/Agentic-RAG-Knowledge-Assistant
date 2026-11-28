import hashlib
import os
from pathlib import Path

import pytest

from app.config import load_config
from app.local_model import OllamaRuntime, get_local_model
from app.question_workflow import QuestionWorkflow
from app.retrieval import Evidence, VersionedEvidence

pytestmark = [
    pytest.mark.credentialed,
    pytest.mark.skipif(
        os.environ.get("RUN_QUESTION_MODEL_TESTS") != "1",
        reason="requires explicit opt-in and a manually prepared local model",
    ),
]


def test_local_question_model_runs_on_non_sensitive_evaluation_evidence() -> None:
    config = load_config()
    source = (
        Path(__file__).parents[2]
        / "evaluation"
        / "feature_002"
        / "sources"
        / "orchard.txt"
    ).read_text(encoding="utf-8")
    evidence = VersionedEvidence(
        evidence=Evidence(source, "orchard.txt", "0", 1.0),
        document_id="smoke-test-document",
        revision="smoke-test-revision",
        digest=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        page=None,
    )

    with OllamaRuntime(config.ollama_executable, config.ollama_host):
        outcome = QuestionWorkflow(get_local_model(config)).run(
            "How many beehives does Cedar Grove Orchard maintain?",
            [evidence],
        )

    assert outcome.status != "failed"
    assert all(
        citation.filename == "orchard.txt"
        for claim in outcome.supported_claims
        for citation in claim.citations
    )
