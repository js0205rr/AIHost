"""Outbound Ollama chat and tool-decision adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ollama import AsyncClient, ResponseError

from app.core.errors import StagedServiceError
from app.core.settings import (
    OLLAMA_ANSWER_NUM_PREDICT,
    OLLAMA_DECISION_NUM_PREDICT,
    OLLAMA_HOST,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    OLLAMA_REQUEST_TIMEOUT_SECONDS,
)


class OllamaGatewayError(StagedServiceError):
    """An expected Ollama connection or generation failure."""


class OllamaClientContext(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None: ...


OllamaClientFactory = Callable[[], OllamaClientContext]


@dataclass(frozen=True)
class OllamaToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class OllamaDecision:
    content: str
    tool_calls: tuple[OllamaToolCall, ...]
    assistant_message: dict[str, Any]


def _default_client_factory() -> AsyncClient:
    return AsyncClient(
        host=OLLAMA_HOST,
        timeout=OLLAMA_REQUEST_TIMEOUT_SECONDS,
    )


def _message_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    if isinstance(message, Mapping):
        return dict(message)
    return {}


class OllamaGateway:
    """One Ollama HTTP client used for a complete agent request."""

    def __init__(
        self,
        client_factory: OllamaClientFactory = _default_client_factory,
    ) -> None:
        self._client_factory = client_factory
        self._client_context: OllamaClientContext | None = None
        self._client: Any = None

    async def __aenter__(self) -> OllamaGateway:
        self._client_context = self._client_factory()
        try:
            self._client = await self._client_context.__aenter__()
        except Exception as exc:
            raise OllamaGatewayError("ollama_connect", "无法连接 Ollama 服务") from exc
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._client_context is not None:
            await self._client_context.__aexit__(exc_type, exc, traceback)

    async def decide(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> OllamaDecision:
        response = await self._chat(
            stage="ollama_decision",
            messages=messages,
            tools=tools,
            temperature=0.0,
            num_predict=OLLAMA_DECISION_NUM_PREDICT,
        )
        message = response.message
        calls: list[OllamaToolCall] = []

        for call in message.tool_calls or []:
            function = call.function
            name = (function.name or "").strip()
            arguments = function.arguments or {}
            calls.append(OllamaToolCall(name=name, arguments=dict(arguments)))

        content = (message.content or "").strip()
        if not calls and not content:
            raise OllamaGatewayError("ollama_decision", "Ollama 未返回回答或工具调用")

        return OllamaDecision(
            content=content,
            tool_calls=tuple(calls),
            assistant_message=_message_dict(message),
        )

    async def generate_final(
        self,
        messages: Sequence[Mapping[str, Any]],
    ) -> str:
        response = await self._chat(
            stage="ollama_final",
            messages=messages,
            tools=None,
            temperature=0.2,
            num_predict=OLLAMA_ANSWER_NUM_PREDICT,
        )
        content = (response.message.content or "").strip()
        if not content:
            raise OllamaGatewayError("ollama_final", "Ollama 未返回最终回答")
        return content

    async def stream_final(
        self,
        messages: Sequence[Mapping[str, Any]],
    ) -> AsyncIterator[str]:
        """Stream final answer text from Ollama one response chunk at a time."""

        emitted = False
        try:
            stream = await self._client.chat(
                model=OLLAMA_MODEL,
                messages=list(messages),
                tools=None,
                stream=True,
                think=False,
                keep_alive=OLLAMA_KEEP_ALIVE,
                options={
                    "temperature": 0.7,
                    "num_predict": OLLAMA_ANSWER_NUM_PREDICT,
                },
            )
            async for chunk in stream:
                content = chunk.message.content or ""
                if content:
                    emitted = True
                    yield content
        except ResponseError as exc:
            if exc.status_code == 404:
                message = f"Ollama 中未找到模型 {OLLAMA_MODEL}"
            else:
                message = "Ollama 流式回答请求失败"
            raise OllamaGatewayError("ollama_final", message) from exc
        except ConnectionError as exc:
            raise OllamaGatewayError("ollama_connect", "无法连接 Ollama 服务") from exc
        except OllamaGatewayError:
            raise
        except Exception as exc:
            raise OllamaGatewayError("ollama_final", "Ollama 流式回答发生未预期错误") from exc

        if not emitted:
            raise OllamaGatewayError("ollama_final", "Ollama 未返回流式回答内容")

    async def _chat(
        self,
        *,
        stage: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] | None,
        temperature: float,
        num_predict: int,
    ) -> Any:
        try:
            return await self._client.chat(
                model=OLLAMA_MODEL,
                messages=list(messages),
                tools=list(tools) if tools else None,
                stream=False,
                think=False,
                keep_alive=OLLAMA_KEEP_ALIVE,
                options={
                    "temperature": temperature,
                    "num_predict": num_predict,
                },
            )
        except ResponseError as exc:
            if exc.status_code == 404:
                message = f"Ollama 中未找到模型 {OLLAMA_MODEL}"
            else:
                message = "Ollama 模型请求失败"
            raise OllamaGatewayError(stage, message) from exc
        except ConnectionError as exc:
            raise OllamaGatewayError("ollama_connect", "无法连接 Ollama 服务") from exc
        except Exception as exc:
            raise OllamaGatewayError(stage, "Ollama 调用发生未预期错误") from exc
