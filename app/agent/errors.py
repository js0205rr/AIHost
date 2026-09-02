"""Agent-layer error categories."""

from app.core.errors import StagedServiceError


class AgentServiceError(StagedServiceError):
    """A safe, client-visible Agent orchestration failure."""


class ToolSchemaError(AgentServiceError):
    def __init__(self, message: str = "MCP 工具参数 Schema 无效") -> None:
        super().__init__(
            "tool_schema",
            message,
            code="invalid_tool_schema",
        )


class ToolArgumentsError(AgentServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(
            "tool_validation",
            message,
            code="invalid_tool_arguments",
        )


class AgentLoopLimitError(AgentServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(
            "tool_limit",
            message,
            code="tool_loop_limit",
        )
