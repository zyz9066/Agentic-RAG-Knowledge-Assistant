import ipaddress
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.observability import (
    LangfuseTraceSink,
    TraceDiagnosticChannel,
    TracePermissionManager,
    TraceRecord,
    TraceStep,
)
from app.retrieval import new_operation_id

pytestmark = [
    pytest.mark.credentialed,
    pytest.mark.skipif(
        os.environ.get("RUN_LANGFUSE_QUESTION_TESTS") != "1",
        reason="requires explicit opt-in and an authorized Langfuse destination",
    ),
]


def test_live_langfuse_exports_only_allowlisted_synthetic_fields(
    tmp_path: Path,
) -> None:
    host = os.environ["LANGFUSE_HOST"]
    public_key = os.environ["LANGFUSE_PUBLIC_KEY"]
    secret_key = os.environ["LANGFUSE_SECRET_KEY"]
    permissions = TracePermissionManager(tmp_path / "permissions.sqlite3", host)
    parsed_host = urlsplit(host).hostname
    try:
        is_loopback = ipaddress.ip_address(parsed_host or "").is_loopback
    except ValueError:
        is_loopback = False
    if is_loopback:
        pytest.skip("local destinations require process-lifetime confirmation")
    permissions.grant_external()
    sink = LangfuseTraceSink(
        permissions,
        TraceDiagnosticChannel(),
        public_key=public_key,
        secret_key=secret_key,
    )
    operation_id = new_operation_id()
    record = TraceRecord(
        operation_id=operation_id,
        name="question",
        status="success",
        duration_ms=1,
        model_id=None,
        steps=(
            TraceStep(
                operation_id=operation_id,
                parent_id=operation_id,
                name="retrieval",
                status="success",
                duration_ms=1,
            ),
        ),
    )

    assert sink.export(record) == "unconfirmed"
