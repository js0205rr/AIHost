"""Compatibility exports for the original MVP MCP module."""

from app.mcp.gateway import (
    ClientFactory,
    McpClientContext,
    McpGateway,
    McpGatewayError,
    McpToolCatalog,
    McpToolDefinition,
    call_current_datetime,
)

__all__ = [
    "ClientFactory",
    "McpClientContext",
    "McpGateway",
    "McpGatewayError",
    "McpToolCatalog",
    "McpToolDefinition",
    "call_current_datetime",
]

