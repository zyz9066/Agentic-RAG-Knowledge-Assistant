import os
from pathlib import Path

import pytest

from app.config import load_config
from app.embeddings import LocalEmbeddings
from app.ingestion import UploadEntry, new_upload_batch, process_batch
from app.retrieval import new_operation_id, retrieve
from app.storage import SQLiteKnowledgeStore


@pytest.mark.skipif(
    os.environ.get("RUN_REAL_MODEL_TESTS") != "1",
    reason="set RUN_REAL_MODEL_TESTS=1 to run the cached-model check",
)
def test_cached_model_retrieves_known_observatory_fact(tmp_path: Path) -> None:
    config = load_config()
    provider = LocalEmbeddings(
        config.embedding_model, config.model_cache_dir, local_files_only=True
    )
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite3")
    sample = Path("data") / "sample-knowledge" / "observatory.txt"
    batch = new_upload_batch([UploadEntry(sample.name, sample.read_bytes())])
    assert process_batch(batch, store, provider)[0].status == "indexed"

    evidence = retrieve(
        store, provider, "Where is the observatory located?", 1, new_operation_id()
    )
    assert len(evidence) == 1
    assert "The observatory is located in Larch Valley." in evidence[0].text
    assert evidence[0].filename == "observatory.txt"
    assert evidence[0].chunk_id == "0"
