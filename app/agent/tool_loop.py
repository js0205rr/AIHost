"""Shared multi-round Agent tool loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, AsyncIterator, Mapping

from app.agent.context import AgentContext
from app.agent.errors import AgentLoopLimitError, ToolArgumentsError
from app.agent.ports import McpGatewayPort, OllamaGatewayPort
from app.agent.tool_validation import validate_tool_arguments
from app.mcp.gateway import McpToolCatalog, McpToolDefinition


class ToolLoopEventType(str, Enum):
    CATALOG_READY = "catalog_ready"
    DECISION_STARTED = "decision_started"
    TOOL_MODE_SELECTED = "tool_mode_selected"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class ToolExecution:
    request_id: str
    round_number: int
    call_index: int
    tool_name: str
    arguments: Mapping[str, Any]
    result: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        object.__setattr__(self, "result", MappingProxyType(dict(self.result)))


@dataclass(frozen=True, slots=True)
class ToolLoopOutcome:
    context: AgentContext
    catalog: McpToolCatalog
    messages: tuple[Mapping[str, Any], ...]
    executions: tuple[ToolExecution, ...]
    terminal_content: str

    @property
    def mode(self) -> str:
        return "tool" if self.executions else "general"


@dataclass(frozen=True, slots=True)
class ToolLoopEvent:
    type: ToolLoopEventType
    round_number: int = 0
    catalog: McpToolCatalog | None = None
    execution: ToolExecution | None = None
    tool_name: str | None = None
    outcome: ToolLoopOutcome | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


def to_ollama_tool(tool: McpToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


async def iterate_tool_loop(
    *,
    context: AgentContext,
    system_prompt: str,
    mcp: McpGatewayPort,
    ollama: OllamaGatewayPort,
    max_rounds: int,
    max_tool_calls: int,
) -> AsyncIterator[ToolLoopEvent]:
    """Yield progress events and finish with exactly one COMPLETED event."""

    if max_rounds < 1 or max_tool_calls < 1:
        raise AgentLoopLimitError("Agent 工具循环限制必须大于零")

    catalog = await mcp.list_allowed_tools()
    yield ToolLoopEvent(ToolLoopEventType.CATALOG_READY, catalog=catalog)

    allowed_by_name = {tool.name: tool for tool in catalog.allowed_tools}
    ollama_tools = [to_ollama_tool(tool) for tool in catalog.allowed_tools]
    if not ollama_tools:
        raise ToolArgumentsError("没有可提供给 Ollama 的白名单工具")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    messages.extend(
        {"role": message.role, "content": message.content}
        for message in context.history
    )
    messages.append({"role": "user", "content": context.message})
    executions: list[ToolExecution] = []
    tool_mode_emitted = False

    for round_number in range(1, max_rounds + 1):
        yield ToolLoopEvent(
            ToolLoopEventType.DECISION_STARTED,
            round_number=round_number,
        )
        decision = await ollama.decide(messages, ollama_tools)

        if not decision.tool_calls:
            outcome = ToolLoopOutcome(
                context=context,
                catalog=catalog,
                messages=tuple(messages),
                executions=tuple(executions),
                terminal_content=decision.content,
            )
            yield ToolLoopEvent(ToolLoopEventType.COMPLETED, outcome=outcome)
            return

        if len(executions) + len(decision.tool_calls) > max_tool_calls:
            raise AgentLoopLimitError("模型请求的工具调用总数超过限制")

        if not tool_mode_emitted:
            tool_mode_emitted = True
            yield ToolLoopEvent(
                ToolLoopEventType.TOOL_MODE_SELECTED,
                round_number=round_number,
            )

        messages.append(decision.assistant_message)

        for call_index, call in enumerate(decision.tool_calls, start=1):
            tool = allowed_by_name.get(call.name)
            if tool is None:
                raise ToolArgumentsError("模型选择了未发现或未授权的工具")

            validate_tool_arguments(tool, call.arguments)
            yield ToolLoopEvent(
                ToolLoopEventType.TOOL_CALL_STARTED,
                round_number=round_number,
                tool_name=call.name,
                metadata={"callIndex": call_index},
            )

            result = await mcp.call_allowed_tool(call.name, call.arguments)
            execution = ToolExecution(
                request_id=context.request_id,
                round_number=round_number,
                call_index=call_index,
                tool_name=call.name,
                arguments=call.arguments,
                result=result,
            )
            executions.append(execution)
            messages.append(
                {
                    "role": "tool",
                    "tool_name": call.name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
            yield ToolLoopEvent(
                ToolLoopEventType.TOOL_CALL_COMPLETED,
                round_number=round_number,
                execution=execution,
            )

    raise AgentLoopLimitError("模型在最大工具轮次内仍未结束工具调用")
