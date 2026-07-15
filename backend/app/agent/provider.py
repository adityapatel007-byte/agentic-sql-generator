"""LLM provider abstraction.

The agent loop only cares about two things:
  1. Send a list of chat messages + tool schemas, get back either text or
     tool_calls.
  2. Do it async.

We use OpenAI's chat/tool wire format directly as the lingua franca — every
serious provider (NVIDIA NIM, OpenRouter, Together) speaks it. This means
messages and tool schemas are plain dicts, and swapping providers is a
one-line change.

v1 impl: NemotronProvider, pointed at NVIDIA's OpenAI-compatible endpoint.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    """A single tool invocation the LLM decided to make."""

    id: str
    name: str
    arguments: dict[str, Any]  # already-parsed JSON


@dataclass
class ProviderResponse:
    """One LLM turn — either free text, tool calls, or both.

    raw_assistant_message is the OpenAI-format dict the loop appends to the
    conversation verbatim so the next turn stays consistent with what the
    model actually emitted (order, ids, etc.).
    """

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_assistant_message: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None


class LLMProvider(Protocol):
    """Every provider (Nemotron, GPT, Kimi, ...) implements this."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> ProviderResponse: ...


class NemotronProvider:
    """OpenAI-compatible client pointed at NVIDIA's NIM endpoint.

    NVIDIA's `integrate.api.nvidia.com/v1` accepts the standard chat/tool
    schema, so the OpenAI async SDK works unchanged — we just override
    base_url and api_key.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        client: Any = None,
    ):
        # Lazy import so tests that inject a fake client don't need the SDK.
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._client = client
        self._model = model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message

        tool_calls: list[ToolCall] = []
        raw_tool_calls: list[dict[str, Any]] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCall(id=tc.id, name=tc.function.name, arguments=args)
            )
            raw_tool_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
            )

        raw: dict[str, Any] = {"role": "assistant", "content": msg.content}
        if raw_tool_calls:
            raw["tool_calls"] = raw_tool_calls

        return ProviderResponse(
            content=msg.content,
            tool_calls=tool_calls,
            raw_assistant_message=raw,
            finish_reason=choice.finish_reason,
        )


def default_provider() -> LLMProvider:
    """Build the provider configured by settings. Fails loud if NVIDIA_API_KEY is unset."""
    from app.config import settings

    if not settings.nvidia_api_key:
        raise RuntimeError(
            "NVIDIA_API_KEY is not set. Add it to backend/.env before running the agent."
        )
    return NemotronProvider(
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
        model=settings.default_model,
    )
