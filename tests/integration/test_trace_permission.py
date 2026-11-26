import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from app.observability import (
    TracePermissionManager,
    TraceRecord,
)


def record() -> TraceRecord:
    return TraceRecord(
        operation_id="d" * 32,
        name="retrieval",
        status="success",
        duration_ms=1,
        model_id=None,
        steps=(),
    )


def test_external_permission_is_opt_in_persistent_and_revocable(tmp_path: Path) -> None:
    database = tmp_path / "trace-permissions.sqlite3"
    sent: list[str] = []
    first = TracePermissionManager(database, "https://trace.example")
    assert first.state == "external_disabled"
    assert (
        first.dispatch(record(), lambda _record, destination: sent.append(destination))
        is False
    )
    assert sent == []

    first.grant_external()
    restarted = TracePermissionManager(database, "https://trace.example")
    assert restarted.state == "external_enabled"
    assert restarted.dispatch(
        record(), lambda _record, destination: sent.append(destination)
    )
    assert sent == ["https://trace.example"]

    restarted.revoke()
    assert first.state == "external_disabled"
    assert first.dispatch(record(), lambda *_args: sent.append("unexpected")) is False
    changed = TracePermissionManager(database, "https://other.example")
    assert changed.state == "external_disabled"


def test_local_confirmation_is_per_process_and_checks_loopback_peer(
    tmp_path: Path,
) -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    destination = f"http://127.0.0.1:{server.getsockname()[1]}"
    manager = TracePermissionManager(tmp_path / "permissions.sqlite3", destination)
    assert manager.state == "local_unconfirmed"
    assert manager.confirm_local(attested=True)
    assert manager.state == "local_confirmed"
    restarted = TracePermissionManager(tmp_path / "permissions.sqlite3", destination)
    assert restarted.state == "local_unconfirmed"
    assert not restarted.confirm_local(attested=False)
    server.close()


def test_hostnames_are_not_treated_as_local_and_proxies_are_bypassed(
    tmp_path: Path,
) -> None:
    manager = TracePermissionManager(
        tmp_path / "permissions.sqlite3", "http://localhost:3000"
    )
    assert manager.state == "external_disabled"
    import httpx

    client = manager.create_httpx_client()
    assert isinstance(client, httpx.Client)
    assert client.trust_env is False
    assert client.follow_redirects is False
    client.close()


def test_route_invalidation_revokes_other_process_confirmations(tmp_path: Path) -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    destination = f"http://127.0.0.1:{server.getsockname()[1]}"
    database = tmp_path / "permissions.sqlite3"
    first = TracePermissionManager(database, destination)
    second = TracePermissionManager(database, destination)
    assert first.confirm_local(attested=True)
    assert second.confirm_local(attested=True)
    first.invalidate_route()
    assert first.state == "local_unconfirmed"
    assert second.state == "local_unconfirmed"
    server.close()


def test_revocation_serializes_against_active_dispatch(tmp_path: Path) -> None:
    database = tmp_path / "permissions.sqlite3"
    manager = TracePermissionManager(database, "https://trace.example")
    manager.grant_external()
    started = threading.Event()
    release = threading.Event()
    revoked = threading.Event()

    def sender(_record: TraceRecord, _destination: str) -> None:
        started.set()
        assert release.wait(5)

    dispatch = threading.Thread(target=lambda: manager.dispatch(record(), sender))
    dispatch.start()
    assert started.wait(5)
    revoke = threading.Thread(target=lambda: (manager.revoke(), revoked.set()))
    revoke.start()
    time.sleep(0.05)
    assert not revoked.is_set()
    release.set()
    dispatch.join(5)
    revoke.join(5)
    assert revoked.is_set()
    assert manager.state == "external_disabled"


def test_revocation_serializes_with_dispatch_in_another_process(tmp_path: Path) -> None:
    database = tmp_path / "permissions.sqlite3"
    marker = tmp_path / "dispatch-started"
    manager = TracePermissionManager(database, "https://trace.example")
    manager.grant_external()
    script = """
import sys
import time
from pathlib import Path
from app.observability import TracePermissionManager, TraceRecord
manager = TracePermissionManager(Path(sys.argv[1]), "https://trace.example")
record = TraceRecord("f" * 32, "retrieval", "success", 1, None, ())
def sender(_record, _destination):
    Path(sys.argv[2]).touch()
    time.sleep(0.5)
assert manager.dispatch(record, sender)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(database), str(marker)]
    )
    try:
        deadline = time.monotonic() + 10
        while (
            not marker.exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert marker.exists(), "child did not start authorized dispatch"
        started = time.monotonic()
        manager.revoke()
        assert time.monotonic() - started >= 0.25
        process.wait(timeout=10)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
    assert manager.state == "external_disabled"
