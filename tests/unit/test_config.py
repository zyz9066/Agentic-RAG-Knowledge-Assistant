from pathlib import Path

import pytest

from app.config import load_config


def test_default_config_keeps_storage_local() -> None:
    config = load_config({})

    assert config.knowledge_dir == Path("data") / "knowledge"
    assert config.model_cache_dir == Path("data") / "model-cache"
    assert config.trace_host is None


def test_config_accepts_environment_values_without_exposing_credentials() -> None:
    config = load_config(
        {
            "KNOWLEDGE_DIR": "private-data",
            "LANGFUSE_HOST": "http://127.0.0.1:3000",
            "LANGFUSE_PUBLIC_KEY": "public-sentinel",
            "LANGFUSE_SECRET_KEY": "secret-sentinel",
        }
    )

    assert config.knowledge_dir == Path("private-data")
    assert config.trace_host == "http://127.0.0.1:3000"
    assert "secret-sentinel" not in repr(config)
    assert "public-sentinel" not in repr(config)


def test_empty_explicit_storage_path_is_rejected() -> None:
    with pytest.raises(ValueError, match="KNOWLEDGE_DIR"):
        load_config({"KNOWLEDGE_DIR": "  "})
