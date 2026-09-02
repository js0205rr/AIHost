"""Allowlisted MCP discovery and invocation boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from mcp import Client

from app.core.errors import StagedServiceError
from app.core.settings import (
    MCP_READ_TIMEOUT_SECONDS,
    MCP_SERVER_URL,
    MCP_TOOL_ALLOWLIST,
    MCP_TOOL_NAME,
)


class McpGatewayError(StagedServiceError):
    """An expected failure at one stage of the MCP call chain."""

    def __init__(
        self,
        stage: str,
        message: str,
        *,
        code: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            stage,
            message,
            code=code or f"mcp_{stage}",
            retryable=retryable,
        )


class McpClientContext(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None: ...


ClientFactory = Callable[[str], McpClientContext]


@dataclass(frozen=True)
class McpToolDefinition:
    """The MCP metadata AIHost is allowed to advertise to a model."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class McpToolCatalog:
    """The full discovery result and its allowlisted subset."""

    discovered_tools: tuple[str, ...]
    allowed_tools: tuple[McpToolDefinition, ...]


def _default_client_factory(server_url: str) -> Client:
    return Client(server_url, read_timeout_seconds=MCP_READ_TIMEOUT_SECONDS)


def _tool_error_message(result: Any) -> str:
    texts = [
        block.text
        for block in getattr(result, "content", [])
        if hasattr(block, "text") and isinstance(block.text, str)
    ]
    return "".join(texts).strip() or "MCP 工具返回错误"


def _normalize_input_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None)
    if schema is None:
        schema = getattr(tool, "input_schema", None)

    if hasattr(schema, "model_dump"):
        schema = schema.model_dump(exclude_none=True)

    if isinstance(schema, Mapping):
        normalized = dict(schema)
    else:
        normalized = {}

    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    return normalized


class McpGateway:
    """A fresh MCP client context used for one AIHost request."""

    def __init__(self, client_factory: ClientFactory = _default_client_factory) -> None:
        self._client_factory = client_factory
        self._client_context: McpClientContext | None = None
        self._client: Any = None

    async def __aenter__(self) -> McpGateway:
        self._client_context = self._client_factory(MCP_SERVER_URL)
        try:
            self._client = await self._client_context.__aenter__()
        except Exception as exc:
            raise McpGatewayError(
                "tools_list",
                "无法连接 MCP Server",
                code="mcp_connect_failed",
                retryable=True,
            ) from exc
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._client_context is not None:
            await self._client_context.__aexit__(exc_type, exc, traceback)

    async def list_allowed_tools(self) -> McpToolCatalog:
        """Run tools/list and retain only tools permitted by AIHost."""

        try:
            listed = await self._client.list_tools()
        except Exception as exc:
            raise McpGatewayError(
                "tools_list",
                "无法从 MCP Server 获取工具列表",
                code="mcp_tools_list_failed",
                retryable=True,
            ) from exc

        discovered = tuple(tool.name for tool in listed.tools)
        allowed = tuple(
            McpToolDefinition(
                name=tool.name,
                description=(getattr(tool, "description", None) or "").strip(),
                input_schema=_normalize_input_schema(tool),
            )
            for tool in listed.tools
            if tool.name in MCP_TOOL_ALLOWLIST
        )

        missing = MCP_TOOL_ALLOWLIST.difference(discovered)
        if missing:
            raise McpGatewayError(
                "tool_validation",
                "MCP Server 未注册 AIHost 白名单中的目标工具",
            )

        return McpToolCatalog(discovered_tools=discovered, allowed_tools=allowed)

    async def call_allowed_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Revalidate the model-selected name, then execute tools/call."""

        if tool_name not in MCP_TOOL_ALLOWLIST:
            raise McpGatewayError("tool_validation", "模型选择的工具不在 AIHost 白名单中")

        try:
            result = await self._client.call_tool(tool_name, dict(arguments or {}))
        except Exception as exc:
            raise McpGatewayError("tool_call", "MCP 工具调用失败") from exc

        if result.is_error:
            raise McpGatewayError("tool_call", _tool_error_message(result))

        structured = result.structured_content
        if not isinstance(structured, dict):
            raise McpGatewayError("tool_call", "MCP 工具未返回结构化 JSON 对象")
        return structured


async def call_current_datetime(
    client_factory: ClientFactory = _default_client_factory,
) -> dict[str, Any]:
    """Preserve the deterministic tools/list then tools/call baseline."""

    started = perf_counter()

    async with McpGateway(client_factory) as gateway:
        catalog = await gateway.list_allowed_tools()
        structured = await gateway.call_allowed_tool(MCP_TOOL_NAME, {})

    return {
        "success": True,
        "toolName": MCP_TOOL_NAME,
        "discoveredTools": list(catalog.discovered_tools),
        "result": structured,
        "elapsedMs": round((perf_counter() - started) * 1000, 2),
    }
