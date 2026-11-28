from __future__ import annotations

import json
from typing import Self

import pytest

from app.config import load_config
from app.local_model import (
    LocalModelError,
    LocalOllamaLLM,
    OllamaRuntime,
    validate_ollama_endpoint,
)

pytestmark = pytest.mark.allow_loopback


def test_local_answer_configuration_has_manual_model_and_loopback_defaults() -> None:
    config = load_config({})

    assert config.answer_model == "qwen2.5:7b"
    assert config.ollama_host == "http://127.0.0.1:11434"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:11434",
        "http://localhost:11434",
        "http://192.168.1.2:11434",
        "http://user@127.0.0.1:11434",
        "http://127.0.0.1:11434/path",
    ],
)
def test_ollama_endpoint_rejects_nonliteral_or_unsafe_addresses(endpoint: str) -> None:
    with pytest.raises(ValueError):
        validate_ollama_endpoint(endpoint)


def test_model_inventory_rejects_missing_or_remote_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = LocalOllamaLLM(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")
    monkeypatch.setattr(
        llm,
        "_request",
        lambda *_args, **_kwargs: {
            "models": [{"name": "qwen2.5:7b", "remote_model": "cloud-model"}]
        },
    )

    with pytest.raises(LocalModelError):
        llm.validate_model()


def test_chat_uses_only_validated_local_model_and_never_downloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = LocalOllamaLLM(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")
    calls: list[tuple[str, str, object]] = []

    def request(
        method: str, path: str, payload: object = None, **_kwargs: object
    ) -> object:
        calls.append((method, path, payload))
        if path == "/api/tags":
            return {"models": [{"name": "qwen2.5:7b", "remote_model": ""}]}
        return {
            "message": {"content": json.dumps({"claims": []})},
            "prompt_eval_count": 12,
            "eval_count": 4,
        }

    monkeypatch.setattr(llm, "_request", request)
    response = llm.call(
        [{"role": "user", "content": "question"}],
        response_model=None,
    )

    assert response == '{"claims": []}'
    assert [path for _, path, _ in calls] == ["/api/tags", "/api/chat"]
    chat = calls[-1][2]
    assert isinstance(chat, dict)
    assert chat["options"]["num_predict"] == 1024
    assert chat["options"]["num_ctx"] == 8192
    assert chat["stream"] is False


def test_input_and_output_limits_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = LocalOllamaLLM(model="qwen2.5:7b", base_url="http://127.0.0.1:11434")
    monkeypatch.setattr(
        llm,
        "_request",
        lambda *_args, **_kwargs: {
            "models": [{"name": "qwen2.5:7b", "remote_model": ""}]
        },
    )
    with pytest.raises(LocalModelError):
        llm.call([{"role": "user", "content": "x" * 9000}])


def test_request_rejects_wrong_peer_and_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __init__(self, status: int) -> None:
            self.status = status

        def read(self, _limit: int) -> bytes:
            return b"redirect"

    class Connection:
        def __init__(
            self,
            peer: tuple[str, int],
            status: int,
            *,
            timeout: float,
        ) -> None:
            self.peer = peer
            self.response = Response(status)
            self.sock = self
            self.timeout = timeout
            self.requested = False

        def connect(self) -> None:
            pass

        def getpeername(self) -> tuple[str, int]:
            return self.peer

        def request(self, *_args: object, **_kwargs: object) -> None:
            self.requested = True

        def getresponse(self) -> Response:
            return self.response

        def close(self) -> None:
            pass

    llm = LocalOllamaLLM(model="qwen2.5:7b")
    redirect = Connection(("127.0.0.1", 11434), 302, timeout=1)
    monkeypatch.setattr(
        "app.local_model.http.client.HTTPConnection",
        lambda *_args, **_kwargs: redirect,
    )
    with pytest.raises(LocalModelError):
        llm._request("GET", "/api/tags")
    assert redirect.requested

    wrong_peer = Connection(("192.0.2.1", 11434), 200, timeout=1)
    monkeypatch.setattr(
        "app.local_model.http.client.HTTPConnection",
        lambda *_args, **_kwargs: wrong_peer,
    )
    with pytest.raises(LocalModelError, match="loopback"):
        llm._request("GET", "/api/tags")
    assert not wrong_peer.requested


def test_request_timeout_has_a_controlled_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TimedOutConnection:
        sock = None

        def connect(self) -> None:
            raise TimeoutError

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "app.local_model.http.client.HTTPConnection",
        lambda *_args, **_kwargs: TimedOutConnection(),
    )
    with pytest.raises(LocalModelError) as error:
        LocalOllamaLLM(model="qwen2.5:7b")._request("GET", "/api/tags")

    assert error.value.code == "local_model_timeout"


def test_owned_runtime_disables_cloud_and_environment_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConnection:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def getpeername(self) -> tuple[str, int]:
            return "127.0.0.1", 11434

    class FakeProcess:
        returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.returncode = 0

        def wait(self, *, timeout: float) -> int:
            return 0

        def kill(self) -> None:
            self.returncode = -9

    connections = 0

    def connect(*_args: object, **_kwargs: object) -> FakeConnection:
        nonlocal connections
        connections += 1
        if connections == 1:
            raise ConnectionRefusedError
        return FakeConnection()

    launch: dict[str, object] = {}

    def start(command: list[str], **kwargs: object) -> FakeProcess:
        launch["command"] = command
        launch["environment"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid")
    monkeypatch.setenv("http_proxy", "http://proxy.invalid")
    monkeypatch.setattr("app.local_model.socket.create_connection", connect)
    monkeypatch.setattr("app.local_model.subprocess.Popen", start)

    with OllamaRuntime("ollama", "http://127.0.0.1:11434") as runtime:
        assert runtime.is_running
        environment = launch["environment"]
        assert isinstance(environment, dict)
        assert environment["OLLAMA_NO_CLOUD"] == "1"
        assert environment["OLLAMA_HOST"] == "127.0.0.1:11434"
        assert "HTTPS_PROXY" not in environment
        assert "http_proxy" not in environment

    assert launch["command"] == ["ollama", "serve"]
    assert not runtime.is_running
