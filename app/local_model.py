"""Loopback-only adapter for a manually prepared Ollama model."""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import subprocess
import time
from collections.abc import Mapping, Sequence
from typing import Any, Self
from urllib.parse import urlsplit

from crewai import BaseLLM
from crewai.llms.base_llm import llm_call_context
from crewai.utilities.types import LLMMessage
from pydantic import BaseModel, PrivateAttr

from app.config import AppConfig, load_config

MAX_CALL_SECONDS = 120
MAX_WORKER_SECONDS = 300
MAX_INPUT_TOKENS = 8192
MAX_OUTPUT_TOKENS = 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
RUNTIME_START_SECONDS = 30


class LocalModelError(RuntimeError):
    """A local model request failed at a controlled boundary."""

    def __init__(self, message: str, code: str = "local_model_unavailable") -> None:
        super().__init__(message)
        self.code = code


class OllamaRuntime:
    """Start and stop one app-owned, cloud-disabled loopback Ollama process."""

    def __init__(self, executable: str, endpoint: str) -> None:
        self.executable = executable
        self.endpoint = endpoint
        self.host, self.port = validate_ollama_endpoint(endpoint)
        self._process: subprocess.Popen[str] | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def __enter__(self) -> Self:
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=0.2
            ) as existing:
                peer = ipaddress.ip_address(existing.getpeername()[0])
                if peer.is_loopback and str(peer) == self.host:
                    raise LocalModelError(
                        "The configured Ollama port is already in use.",
                        "local_model_config_invalid",
                    )
        except OSError:
            pass

        environment = os.environ.copy()
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            environment.pop(key, None)
        environment["OLLAMA_HOST"] = f"{self.host}:{self.port}"
        environment["OLLAMA_NO_CLOUD"] = "1"
        try:
            self._process = self._launch(environment)
        except OSError as exc:
            raise LocalModelError(
                "The manually installed Ollama executable could not be started.",
                "local_model_unavailable",
            ) from exc

        deadline = time.monotonic() + RUNTIME_START_SECONDS
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                self._stop()
                raise LocalModelError(
                    "The app-owned Ollama process could not bind its loopback port.",
                    "local_model_config_invalid",
                )
            try:
                with socket.create_connection(
                    (self.host, self.port), timeout=0.2
                ) as connection:
                    peer = ipaddress.ip_address(connection.getpeername()[0])
                    if peer.is_loopback and str(peer) == self.host:
                        return self
            except OSError:
                time.sleep(0.1)
        self._stop()
        raise LocalModelError(
            "The app-owned Ollama process did not become ready.",
            "local_model_unavailable",
        )

    def __exit__(self, *_exc: object) -> None:
        self._stop()

    def _stop(self) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._process = None

    def _launch(self, environment: dict[str, str]) -> subprocess.Popen[str]:
        command = [self.executable, "serve"]
        common = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "env": environment,
            "shell": False,
            "close_fds": True,
        }
        if os.name == "nt":
            return subprocess.Popen(
                command,
                **common,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        return subprocess.Popen(command, **common, start_new_session=True)


def validate_ollama_endpoint(endpoint: str) -> tuple[str, int]:
    """Accept only a bare HTTP URL using the literal IPv4 loopback address."""
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port or 11434
    except ValueError as exc:
        raise ValueError("Ollama endpoint must use literal IPv4 loopback.") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or not 1 <= port <= 65535
    ):
        raise ValueError("Ollama endpoint must use literal IPv4 loopback.")
    try:
        if not ipaddress.ip_address(parsed.hostname).is_loopback:
            raise ValueError("Ollama endpoint must use literal IPv4 loopback.")
    except ValueError as exc:
        raise ValueError("Ollama endpoint must use literal IPv4 loopback.") from exc
    return parsed.hostname, port


class LocalOllamaLLM(BaseLLM):
    """CrewAI LLM that talks directly to one validated local Ollama model."""

    model: str
    base_url: str | None = "http://127.0.0.1:11434"
    _last_usage: dict[str, int] = PrivateAttr(default_factory=dict)

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
    ) -> None:
        validate_ollama_endpoint(base_url)
        if not model or "/" in model or model.endswith(":cloud"):
            raise ValueError("A manually prepared local model name is required.")
        super().__init__(model=model, base_url=base_url.rstrip("/"))

    @property
    def model_id(self) -> str:
        return self.model

    @property
    def last_usage(self) -> dict[str, int]:
        return self._last_usage.copy()

    @property
    def _address(self) -> tuple[str, int]:
        if self.base_url is None:
            raise LocalModelError(
                "The local model endpoint is not configured.",
                "local_model_config_invalid",
            )
        return validate_ollama_endpoint(self.base_url)

    def _request(
        self,
        method: str,
        path: str,
        payload: object = None,
        *,
        timeout: float = MAX_CALL_SECONDS,
    ) -> Mapping[str, Any]:
        host, port = self._address
        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        connection = http.client.HTTPConnection(host, port, timeout=timeout)
        try:
            connection.connect()
            if connection.sock is None:
                raise LocalModelError("The local model service is unavailable.")
            peer = ipaddress.ip_address(connection.sock.getpeername()[0])
            if not peer.is_loopback or str(peer) != host:
                raise LocalModelError(
                    "The local model connection did not reach loopback.",
                    "local_model_config_invalid",
                )
            connection.request(
                method,
                path,
                body=body,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if response.status != 200 or len(raw) > MAX_RESPONSE_BYTES:
                raise LocalModelError("The local model service returned an error.")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise LocalModelError("The local model returned an invalid response.")
            return result
        except LocalModelError:
            raise
        except TimeoutError as exc:
            raise LocalModelError(
                "The local model request timed out.", "local_model_timeout"
            ) from exc
        except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
            raise LocalModelError("The local model service is unavailable.") from exc
        finally:
            connection.close()

    def validate_model(self) -> None:
        inventory = self._request("GET", "/api/tags", timeout=5)
        models = inventory.get("models")
        if not isinstance(models, list):
            raise LocalModelError("The local model inventory is invalid.")
        matching = [
            item
            for item in models
            if isinstance(item, dict) and item.get("name") == self.model
        ]
        if (
            len(matching) != 1
            or matching[0].get("remote_model") not in (None, "")
            or matching[0].get("remote_host") not in (None, "")
            or matching[0].get("is_remote") is True
        ):
            raise LocalModelError(
                "The configured local model is unavailable or not local.",
                "local_model_unavailable",
            )

    @staticmethod
    def _message_text(messages: str | Sequence[Mapping[str, Any]]) -> str:
        if isinstance(messages, str):
            return messages
        return "\n".join(
            str(message.get("content", ""))
            for message in messages
            if isinstance(message, Mapping)
        )

    def call(
        self,
        messages: str | list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: type[BaseModel] | None = None,
        **_kwargs: Any,
    ) -> str | Any:
        self._last_usage = {}
        if tools:
            raise LocalModelError(
                "The local answer model does not accept tools.",
                "local_model_config_invalid",
            )
        prompt = self._message_text(messages)
        # UTF-8 bytes are a conservative upper bound for tokenizer pieces.
        if len(prompt.encode("utf-8")) > MAX_INPUT_TOKENS:
            raise LocalModelError(
                "The question and evidence exceed the local model input limit.",
                "input_too_large",
            )
        with llm_call_context():
            self._emit_call_started_event(
                messages=messages,
                tools=tools,
                callbacks=callbacks,
                available_functions=available_functions,
                from_task=from_task,
                from_agent=from_agent,
            )
            self.validate_model()
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {
                        "role": str(message.get("role", "user")),
                        "content": str(message.get("content", "")),
                    }
                    for message in messages
                ]
                if not isinstance(messages, str)
                else [{"role": "user", "content": messages}],
                "stream": False,
                "options": {
                    "num_ctx": MAX_INPUT_TOKENS,
                    "num_predict": MAX_OUTPUT_TOKENS,
                },
            }
            if response_model is not None:
                payload["format"] = response_model.model_json_schema()
            response = self._request(
                "POST",
                "/api/chat",
                payload,
                timeout=MAX_CALL_SECONDS,
            )
            message = response.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str):
                raise LocalModelError("The local model returned an invalid response.")
            if response_model is not None:
                try:
                    structured = response_model.model_validate_json(content)
                except ValueError as exc:
                    raise LocalModelError(
                        "The local model returned malformed structured output.",
                        "workflow_failed",
                    ) from exc
            else:
                structured = content
            prompt_tokens = response.get("prompt_eval_count", 0)
            output_tokens = response.get("eval_count", 0)
            prompt_tokens = (
                prompt_tokens
                if isinstance(prompt_tokens, int)
                and not isinstance(prompt_tokens, bool)
                and prompt_tokens >= 0
                else 0
            )
            output_tokens = (
                output_tokens
                if isinstance(output_tokens, int)
                and not isinstance(output_tokens, bool)
                and output_tokens >= 0
                else 0
            )
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": prompt_tokens + output_tokens,
            }
            self._last_usage = {
                "input_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "total_tokens": prompt_tokens + output_tokens,
            }
            self._track_token_usage_internal(usage)
            from crewai.events.types.llm_events import LLMCallType

            self._emit_call_completed_event(
                response=content,
                call_type=LLMCallType.LLM_CALL,
                from_task=from_task,
                from_agent=from_agent,
                messages=messages,
                usage=usage,
            )
            return structured

    async def acall(self, *args: Any, **kwargs: Any) -> str | Any:
        return self.call(*args, **kwargs)

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return MAX_INPUT_TOKENS


def get_local_model(config: AppConfig | None = None) -> LocalOllamaLLM:
    """Create the configured adapter without starting or downloading a model."""
    settings = config or load_config()
    return LocalOllamaLLM(
        model=settings.answer_model,
        base_url=settings.ollama_host,
    )
