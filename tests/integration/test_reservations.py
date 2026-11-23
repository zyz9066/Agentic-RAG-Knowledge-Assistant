import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.storage import Chunk, ReservationConflict, SQLiteKnowledgeStore


def test_same_name_conflicts_but_other_names_and_retries_succeed(
    tmp_path: Path,
) -> None:
    first = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    second = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")

    with first.reserve("facts.txt"):
        with pytest.raises(ReservationConflict), second.reserve("facts.txt"):
            pytest.fail("overlapping reservations must not proceed")
        with second.reserve("Facts.txt"):
            pass
        with second.reserve("other.txt"):
            pass
    with second.reserve("facts.txt"):
        pass


def test_different_threads_cannot_reserve_the_same_filename(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")

    def attempt() -> None:
        with store.reserve("facts.txt"):
            pytest.fail("another thread holds the reservation")

    with (
        store.reserve("facts.txt"),
        ThreadPoolExecutor(max_workers=1) as executor,
        pytest.raises(ReservationConflict),
    ):
        executor.submit(attempt).result(timeout=5)


def test_unexpected_lock_error_does_not_allow_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")

    def fail(_file: object) -> None:
        raise PermissionError("injected lock failure")

    monkeypatch.setattr("app.storage._try_lock", fail)
    with pytest.raises(PermissionError), store.reserve("facts.txt"):
        pytest.fail("processing must not proceed without a reservation")


@pytest.mark.parametrize("commit", [False, True])
def test_process_interruption_releases_reservation_and_preserves_commits(
    tmp_path: Path, commit: bool
) -> None:
    path = tmp_path / "knowledge.sqlite3"
    marker = tmp_path / "ready"
    store = SQLiteKnowledgeStore(path)
    store.replace("facts.txt", "model", [Chunk("0", "old", (1.0, 0.0), None)])
    code = """
import sys
import time
from pathlib import Path
from app.storage import Chunk, SQLiteKnowledgeStore
store = SQLiteKnowledgeStore(Path(sys.argv[1]))
with store.reserve("facts.txt"):
    if sys.argv[3] == "yes":
        store.replace("facts.txt", "model", [Chunk("0", "new", (1.0, 0.0), None)])
    Path(sys.argv[2]).touch()
    time.sleep(60)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(path), str(marker), "yes" if commit else "no"]
    )
    try:
        deadline = time.monotonic() + 10
        while (
            not marker.exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert marker.exists(), "child process did not acquire the reservation"
        with pytest.raises(ReservationConflict), store.reserve("facts.txt"):
            pytest.fail("another process holds the reservation")
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)

    deadline = time.monotonic() + 5
    while True:
        try:
            with store.reserve("facts.txt"):
                assert [item.text for item in store.read_chunks("model", 2)] == [
                    "new" if commit else "old"
                ]
            break
        except ReservationConflict:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)
