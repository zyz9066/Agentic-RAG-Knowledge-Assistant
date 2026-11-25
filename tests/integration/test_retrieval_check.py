import json
from pathlib import Path
from typing import ClassVar

import pytest

from app import retrieval_check
from app.storage import Chunk, SQLiteKnowledgeStore


class StubLocalEmbeddings:
    model_id = "test-embedding-v1"
    dimension = 2
    max_tokens = 32
    instances: ClassVar[list["StubLocalEmbeddings"]] = []

    def __init__(self, _model_name: str, _cache_dir: Path) -> None:
        self.instances.append(self)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def _configure_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KNOWLEDGE_DIR", str(tmp_path / "knowledge"))
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "models"))
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    StubLocalEmbeddings.instances.clear()
    monkeypatch.setattr(retrieval_check, "LocalEmbeddings", StubLocalEmbeddings)


def test_retrieval_check_prints_provenance_json_and_safe_trace_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _configure_command(monkeypatch, tmp_path)
    store = SQLiteKnowledgeStore(tmp_path / "knowledge" / "knowledge.sqlite3")
    store.replace(
        "facts.txt",
        "test-embedding-v1",
        [Chunk("0", "the observatory is north", (1.0, 0.0), None)],
    )

    assert retrieval_check.main(["where is the observatory?", "--limit", "1"]) == 0
    captured = capsys.readouterr()

    assert json.loads(captured.out) == [
        {
            "text": "the observatory is north",
            "filename": "facts.txt",
            "chunk_id": "0",
            "score": 1.0,
        }
    ]
    assert "Trace export is unavailable" in captured.err
    assert "where is the observatory?" not in captured.err


def test_retrieval_check_reports_invalid_query_and_has_help(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _configure_command(monkeypatch, tmp_path)

    assert retrieval_check.main(["   "]) == 1
    assert "question" in capsys.readouterr().err.lower()
    assert StubLocalEmbeddings.instances == []

    with pytest.raises(SystemExit) as exit_info:
        retrieval_check.main(["--help"])
    assert exit_info.value.code == 0
    assert "usage:" in capsys.readouterr().out.lower()
