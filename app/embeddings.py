"""Embedding provider contract and local FastEmbed adapter."""

import hashlib
import math
from pathlib import Path
from typing import Protocol

from fastembed.text.onnx_embedding import OnnxTextEmbedding
from tokenizers import Tokenizer


class EmbeddingError(RuntimeError):
    """The configured embedding provider could not produce valid vectors."""


class EmbeddingProvider(Protocol):
    model_id: str
    dimension: int
    max_tokens: int
    sends_text_externally: bool
    provider_id: str
    data_description: str

    def token_count(self, text: str) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbeddings:
    """Use a local ONNX model and an untruncated copy of its tokenizer."""

    sends_text_externally = False
    provider_id = "local-fastembed"
    data_description = "Document text is processed locally."

    def __init__(
        self, model_name: str, cache_dir: Path, *, local_files_only: bool = False
    ) -> None:
        try:
            model = OnnxTextEmbedding(
                model_name=model_name,
                cache_dir=str(cache_dir),
                local_files_only=local_files_only,
                cuda=False,
            )
            tokenizer = model.tokenizer
            if tokenizer is None or tokenizer.truncation is None:
                raise ValueError("model tokenizer or token limit is unavailable")
            max_tokens = tokenizer.truncation["max_length"]
            if not isinstance(max_tokens, int) or max_tokens <= 0:
                raise ValueError("model token limit is invalid")
            self.max_tokens = max_tokens
            self._tokenizer = Tokenizer.from_str(tokenizer.to_str())
            self._tokenizer.no_truncation()
            self._tokenizer.no_padding()
            description = model.model_description
            dimension = description.dim
            if not isinstance(dimension, int) or dimension <= 0:
                raise ValueError("model embedding dimension is invalid")
            self.dimension = dimension
            digest = hashlib.sha256()
            digest.update(self._tokenizer.to_str().encode("utf-8"))
            files: set[str] = {description.model_file, *description.additional_files}
            for name in (
                "config.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
            ):
                if (model._model_dir / name).is_file():
                    files.add(name)
            for name in sorted(files):
                digest.update(name.encode("utf-8"))
                with (model._model_dir / name).open("rb") as source:
                    digest.update(hashlib.file_digest(source, "sha256").digest())
            self.model_id = f"{model_name}@sha256:{digest.hexdigest()}"
            self._model = model
        except (OSError, RuntimeError, ValueError, ImportError):
            raise EmbeddingError(
                "The configured local embedding model is unavailable."
            ) from None

    def token_count(self, text: str) -> int:
        """Count all tokens including special tokens without truncating."""
        return len(self._tokenizer.encode(text).ids)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if any(self.token_count(text) > self.max_tokens for text in texts):
            raise EmbeddingError("Text exceeds the embedding model's token limit.")
        try:
            vectors = [
                [float(value) for value in vector]
                for vector in self._model.embed(texts)
            ]
        except (OSError, RuntimeError, ValueError):
            raise EmbeddingError("The local embedding model failed.") from None
        if len(vectors) != len(texts) or any(
            len(vector) != self.dimension
            or not all(math.isfinite(value) for value in vector)
            or not any(vector)
            for vector in vectors
        ):
            raise EmbeddingError("The embedding model returned invalid vectors.")
        return vectors
