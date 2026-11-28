"""Deterministic, offline LLM substitute for the CrewAI 1.15.x API."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

from crewai import BaseLLM
from crewai.llms.base_llm import llm_call_context
from pydantic import BaseModel, Field, PrivateAttr


class StubLLM(BaseLLM):
    """Return queued outputs and record each prompt without provider access."""

    model: str = "stub/deterministic"
    provider: str = "stub"
    responses: list[Any] = Field(default_factory=list)
    responder: Callable[..., Any] | None = None
    default_response: str = "Stub response."
    emit_events: bool = True
    native_structured_output: bool = True

    _cursor: list[int] = PrivateAttr(default_factory=lambda: [0])
    _calls: list[dict[str, Any]] = PrivateAttr(default_factory=list)

    def __init__(self, **data: Any) -> None:
        data.setdefault("model", "stub/deterministic")
        super().__init__(**data)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self._calls

    def reset(self) -> None:
        self._cursor[0] = 0
        self._calls.clear()

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, BaseModel):
            return value.model_dump_json()
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    def _next(self, messages: Any, response_model: type[BaseModel] | None) -> str:
        if self._cursor[0] < len(self.responses):
            response = self.responses[self._cursor[0]]
            self._cursor[0] += 1
            if callable(response) and not isinstance(response, type):
                response = response(messages, response_model)
            return self._text(response)
        if self.responder is not None:
            return self._text(self.responder(messages, response_model))
        return self.default_response

    def call(
        self,
        messages: Any,
        tools: list[dict[str, Any]] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> Any:
        with llm_call_context():
            if self.emit_events:
                self._emit_call_started_event(
                    messages=messages,
                    tools=tools,
                    callbacks=callbacks,
                    available_functions=available_functions,
                    from_task=from_task,
                    from_agent=from_agent,
                )
            text = self._next(messages, response_model)
            self._calls.append(
                {
                    "messages": copy.deepcopy(messages),
                    "response_model": response_model,
                    "tools": tools,
                    "response": text,
                }
            )
            usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
            self._track_token_usage_internal(usage)
            if self.emit_events:
                from crewai.events.types.llm_events import LLMCallType

                self._emit_call_completed_event(
                    response=text,
                    call_type=LLMCallType.LLM_CALL,
                    from_task=from_task,
                    from_agent=from_agent,
                    messages=messages,
                    usage=usage,
                )
            if self.native_structured_output and response_model is not None:
                try:
                    return response_model.model_validate_json(text)
                except ValueError:
                    pass
            return text

    async def acall(self, *args: Any, **kwargs: Any) -> Any:
        return self.call(*args, **kwargs)

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 8192


def prompt_text(call: dict[str, Any]) -> str:
    messages = call["messages"]
    if isinstance(messages, str):
        return messages
    return "\n".join(str(message.get("content", "")) for message in messages)
