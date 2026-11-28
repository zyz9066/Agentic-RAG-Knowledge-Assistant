"""Environment-based configuration for local indexing and tracing."""

import ipaddress
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
    answer_model: str
    ollama_host: str
    ollama_executable: str
    trace_host: str | None
    trace_public_key: str | None = field(repr=False)
    trace_secret_key: str | None = field(repr=False)


def is_loopback_bind(address: str | None) -> bool:
    """Accept only the explicit IPv4 loopback address for the local UI."""
    return address == "127.0.0.1"


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

    answer_model = _value(settings, "ANSWER_MODEL", "qwen2.5:7b")
    if "/" in answer_model or answer_model.endswith(":cloud"):
        raise ValueError("ANSWER_MODEL must identify a manually prepared local model")
    ollama_host = _value(settings, "OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    parsed_ollama = urlsplit(ollama_host)
    try:
        is_loopback = ipaddress.ip_address(parsed_ollama.hostname or "").is_loopback
        port = parsed_ollama.port
    except ValueError:
        is_loopback = False
        port = None
    if (
        parsed_ollama.scheme != "http"
        or not is_loopback
        or parsed_ollama.hostname != "127.0.0.1"
        or parsed_ollama.username is not None
        or parsed_ollama.password is not None
        or parsed_ollama.path
        or parsed_ollama.query
        or parsed_ollama.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("OLLAMA_HOST must use the literal IPv4 loopback address")

    return AppConfig(
        knowledge_dir=Path(
            _value(settings, "KNOWLEDGE_DIR", str(Path("data") / "knowledge"))
        ).expanduser(),
        model_cache_dir=Path(
            _value(settings, "EMBEDDING_CACHE_DIR", str(Path("data") / "model-cache"))
        ).expanduser(),
        embedding_model=_value(settings, "EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        answer_model=answer_model,
        ollama_host=ollama_host,
        ollama_executable=_value(settings, "OLLAMA_EXECUTABLE", "ollama"),
        trace_host=host,
        trace_public_key=settings.get("LANGFUSE_PUBLIC_KEY", "").strip() or None,
        trace_secret_key=settings.get("LANGFUSE_SECRET_KEY", "").strip() or None,
    )
