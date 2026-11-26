from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from tokenizers.processors import TemplateProcessing

from app.embeddings import EmbeddingError, LocalEmbeddings


@pytest.fixture
def fake_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    tokenizer = Tokenizer(
        WordLevel(
            {"[UNK]": 0, "one": 1, "two": 2, "three": 3, "[CLS]": 4, "[SEP]": 5},
            unk_token="[UNK]",
        )
    )
    tokenizer.pre_tokenizer = Whitespace()
    tokenizer.post_processor = TemplateProcessing(
        single="[CLS] $A [SEP]", special_tokens=[("[CLS]", 4), ("[SEP]", 5)]
    )
    tokenizer.enable_truncation(max_length=4)
    (tmp_path / "model.onnx").write_bytes(b"model-v1")
    model = SimpleNamespace(
        tokenizer=tokenizer,
        _model_dir=tmp_path,
        model_description=SimpleNamespace(
            dim=2, model_file="model.onnx", additional_files=[]
        ),
        embed=lambda texts: [np.array([1.0, 0.0], dtype=np.float32) for _ in texts],
    )
    monkeypatch.setattr("app.embeddings.OnnxTextEmbedding", lambda **_kwargs: model)
    return model


def test_model_identity_tracks_files_and_token_count_never_truncates(
    tmp_path: Path, fake_model: SimpleNamespace
) -> None:
    first = LocalEmbeddings("test-model", tmp_path, local_files_only=True)
    assert first.max_tokens == 4
    assert first.token_count("one two three") == 5
    assert first.embed(["one two"]) == [[1.0, 0.0]]
    with pytest.raises(EmbeddingError):
        first.embed(["one two three"])

    (tmp_path / "model.onnx").write_bytes(b"model-v2")
    second = LocalEmbeddings("test-model", tmp_path, local_files_only=True)
    assert first.model_id != second.model_id
    assert not first.sends_text_externally


@pytest.mark.parametrize(
    "vector", [[0.0, 0.0], [float("nan"), 1.0], [float("inf"), 1.0], [1.0]]
)
def test_invalid_provider_vectors_fail_explicitly(
    tmp_path: Path, fake_model: SimpleNamespace, vector: list[float]
) -> None:
    fake_model.embed = lambda _texts: [np.array(vector, dtype=np.float32)]
    provider = LocalEmbeddings("test-model", tmp_path, local_files_only=True)
    with pytest.raises(EmbeddingError):
        provider.embed(["one"])


def test_missing_model_is_a_safe_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**_kwargs: object) -> None:
        raise OSError("sensitive path")

    monkeypatch.setattr("app.embeddings.OnnxTextEmbedding", fail)
    with pytest.raises(EmbeddingError) as error:
        LocalEmbeddings("missing", tmp_path, local_files_only=True)
    assert "sensitive path" not in str(error.value)


def test_missing_cached_fastembed_model_fails_without_downloading(
    tmp_path: Path,
) -> None:
    with pytest.raises(EmbeddingError):
        LocalEmbeddings("BAAI/bge-small-en-v1.5", tmp_path, local_files_only=True)
