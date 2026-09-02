"""Structural interfaces consumed by the Agent application layer."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any, Protocol, Self

from app.integrations.ollama import OllamaDecision
from app.mcp.gateway import McpToolCatalog


class McpGatewayPort(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None: ...

    async def list_allowed_tools(self) -> McpToolCatalog: ...

    async def call_allowed_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class OllamaGatewayPort(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None: ...

    async def decide(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> OllamaDecision: ...

    async def generate_final(self, messages: Sequence[Mapping[str, Any]]) -> str: ...

    def stream_final(
        self,
        messages: Sequence[Mapping[str, Any]],
    ) -> AsyncIterator[str]: ...


McpGatewayFactory = Callable[[], McpGatewayPort]
OllamaGatewayFactory = Callable[[], OllamaGatewayPort]
