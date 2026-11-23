"""Environment-based configuration for local indexing and tracing."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from os import environ
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class AppConfig:
    knowledge_dir: Path
    model_cache_dir: Path
    embedding_model: str
    trace_host: str | None
    trace_public_key: str | None = field(repr=False)
    trace_secret_key: str | None = field(repr=False)


def _value(values: Mapping[str, str], name: str, default: str) -> str:
    value = values.get(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def load_config(values: Mapping[str, str] | None = None) -> AppConfig:
    """Load settings without creating directories or contacting services."""
    settings = environ if values is None else values
    host = settings.get("LANGFUSE_HOST", "").strip() or None
    if host is not None:
        parsed = urlsplit(host)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("LANGFUSE_HOST must be an HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("LANGFUSE_HOST must not contain credentials")

    return AppConfig(
        knowledge_dir=Path(
            _value(settings, "KNOWLEDGE_DIR", str(Path("data") / "knowledge"))
        ).expanduser(),
        model_cache_dir=Path(
            _value(settings, "EMBEDDING_CACHE_DIR", str(Path("data") / "model-cache"))
        ).expanduser(),
        embedding_model=_value(settings, "EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        trace_host=host,
        trace_public_key=settings.get("LANGFUSE_PUBLIC_KEY", "").strip() or None,
        trace_secret_key=settings.get("LANGFUSE_SECRET_KEY", "").strip() or None,
    )
