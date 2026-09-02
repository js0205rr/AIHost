"""Application-layer Ollama and MCP orchestration for the migration MVP."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any

from app.agent.context import AgentContext
from app.agent.errors import AgentServiceError
from app.agent.ports import McpGatewayFactory, OllamaGatewayFactory
from app.agent.tool_loop import (
    ToolLoopEvent,
    ToolLoopEventType,
    ToolLoopOutcome,
    iterate_tool_loop,
)
from app.core.settings import (
    AGENT_MAX_TOOL_CALLS,
    AGENT_MAX_TOOL_ROUNDS,
    OLLAMA_MODEL,
)
from app.integrations.ollama import OllamaGateway
from app.mcp.gateway import McpGateway


SYSTEM_PROMPT = (
    "你是 CUBIC AIHost 的工具调用助手。"
    "请根据用户问题和提供的工具说明，决定是否需要调用工具。"
    "只有在工具能够提供必要实时信息时才调用；普通问候或无需实时数据的问题直接回答。"
    "每次获得工具结果后，应判断是否还需要其他工具；不需要时直接返回回答。"
    "不得编造工具名、参数或工具结果。请始终使用简体中文回答。"
)

FINAL_SYSTEM_PROMPT = "你是一个专业的 AI 助手，请直接回答用户当前的问题。请始终使用简体中文回答。"


def _default_mcp_gateway_factory() -> McpGateway:
    return McpGateway()


def _default_ollama_gateway_factory() -> OllamaGateway:
    return OllamaGateway()


AgentInput = str | AgentContext


def _as_context(value: AgentInput) -> AgentContext:
    return value if isinstance(value, AgentContext) else AgentContext(message=value)


def _build_final_messages(outcome: ToolLoopOutcome) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": FINAL_SYSTEM_PROMPT},
    ]
    messages.extend(dict(message) for message in outcome.messages[1:])
    return messages


def _tool_call_payload(outcome: ToolLoopOutcome) -> list[dict[str, Any]]:
    return [
        {
            "round": execution.round_number,
            "callIndex": execution.call_index,
            "toolName": execution.tool_name,
            "arguments": dict(execution.arguments),
            "result": dict(execution.result),
        }
        for execution in outcome.executions
    ]


def _require_outcome(outcome: ToolLoopOutcome | None) -> ToolLoopOutcome:
    if outcome is None:
        raise AgentServiceError(
            "tool_loop",
            "Agent 工具循环未返回完成结果",
            code="missing_tool_loop_outcome",
        )
    return outcome


async def stream_agent_events(
    user_message: AgentInput,
    mcp_gateway_factory: McpGatewayFactory = _default_mcp_gateway_factory,
    ollama_gateway_factory: OllamaGatewayFactory = _default_ollama_gateway_factory,
) -> AsyncIterator[dict[str, Any]]:
    """Yield existing SSE payload types from the shared multi-round tool loop."""

    context = _as_context(user_message)
    yield {"type": "meta", "model": OLLAMA_MODEL}

    async with mcp_gateway_factory() as mcp, ollama_gateway_factory() as ollama:
        yield {
            "type": "status",
            "stage": "tools_list",
            "content": "正在获取 MCP 工具列表...",
        }

        outcome: ToolLoopOutcome | None = None
        async for event in iterate_tool_loop(
            context=context,
            system_prompt=SYSTEM_PROMPT,
            mcp=mcp,
            ollama=ollama,
            max_rounds=AGENT_MAX_TOOL_ROUNDS,
            max_tool_calls=AGENT_MAX_TOOL_CALLS,
        ):
            if event.type is ToolLoopEventType.DECISION_STARTED:
                yield {
                    "type": "status",
                    "stage": "ollama_decision",
                    "content": "正在进行 Ollama 工具决策...",
                }
            elif event.type is ToolLoopEventType.TOOL_MODE_SELECTED:
                yield {"type": "classify", "mode": "tool", "label": "工具调用"}
            elif event.type is ToolLoopEventType.TOOL_CALL_STARTED:
                yield {
                    "type": "status",
                    "stage": "tool_call",
                    "content": f"正在调用：{event.tool_name}...",
                }
            elif event.type is ToolLoopEventType.TOOL_CALL_COMPLETED:
                execution = event.execution
                if execution is None:
                    raise AgentServiceError(
                        "tool_loop",
                        "工具循环缺少执行结果",
                        code="missing_tool_execution",
                    )
                yield {
                    "type": "tool_result",
                    "toolName": execution.tool_name,
                    "displayName": execution.tool_name,
                    "content": json.dumps(dict(execution.result), ensure_ascii=False),
                }
            elif event.type is ToolLoopEventType.COMPLETED:
                outcome = event.outcome

        outcome = _require_outcome(outcome)
        if outcome.mode == "general":
            yield {"type": "classify", "mode": "general", "label": "通用对话"}

        yield {
            "type": "status",
            "stage": "ollama_final",
            "content": "正在生成回答...",
        }
        async for content in ollama.stream_final(_build_final_messages(outcome)):
            yield {"type": "response", "content": content}


async def ask_agent(
    user_message: AgentInput,
    mcp_gateway_factory: McpGatewayFactory = _default_mcp_gateway_factory,
    ollama_gateway_factory: OllamaGatewayFactory = _default_ollama_gateway_factory,
) -> dict[str, Any]:
    """Execute a bounded multi-round tool loop and return one JSON result."""

    context = _as_context(user_message)
    started = perf_counter()
    stages: list[dict[str, Any]] = []

    async with mcp_gateway_factory() as mcp, ollama_gateway_factory() as ollama:
        outcome: ToolLoopOutcome | None = None
        async for event in iterate_tool_loop(
            context=context,
            system_prompt=SYSTEM_PROMPT,
            mcp=mcp,
            ollama=ollama,
            max_rounds=AGENT_MAX_TOOL_ROUNDS,
            max_tool_calls=AGENT_MAX_TOOL_CALLS,
        ):
            _append_stage(stages, event)
            if event.type is ToolLoopEventType.COMPLETED:
                outcome = event.outcome

        outcome = _require_outcome(outcome)
        tool_calls = _tool_call_payload(outcome)

        if outcome.mode == "general":
            return {
                "success": True,
                "mode": "general",
                "model": OLLAMA_MODEL,
                "discoveredTools": list(outcome.catalog.discovered_tools),
                "advertisedTools": [tool.name for tool in outcome.catalog.allowed_tools],
                "selectedTool": None,
                "toolArguments": None,
                "toolResult": None,
                "toolCalls": [],
                "answer": outcome.terminal_content,
                "stages": stages,
                "elapsedMs": round((perf_counter() - started) * 1000, 2),
            }

        answer = await ollama.generate_final(_build_final_messages(outcome))
        stages.append({"stage": "ollama_final", "success": True})

    first_execution = outcome.executions[0]
    return {
        "success": True,
        "mode": "tool",
        "model": OLLAMA_MODEL,
        "discoveredTools": list(outcome.catalog.discovered_tools),
        "advertisedTools": [tool.name for tool in outcome.catalog.allowed_tools],
        "selectedTool": first_execution.tool_name,
        "toolArguments": dict(first_execution.arguments),
        "toolResult": dict(first_execution.result),
        "toolCalls": tool_calls,
        "answer": answer,
        "stages": stages,
        "elapsedMs": round((perf_counter() - started) * 1000, 2),
    }


def _append_stage(stages: list[dict[str, Any]], event: ToolLoopEvent) -> None:
    if event.type is ToolLoopEventType.CATALOG_READY:
        stages.append({"stage": "tools_list", "success": True})
    elif event.type is ToolLoopEventType.DECISION_STARTED:
        stages.append(
            {
                "stage": "ollama_decision",
                "round": event.round_number,
                "success": True,
            }
        )
    elif event.type is ToolLoopEventType.TOOL_CALL_STARTED:
        stages.append(
            {
                "stage": "tool_validation",
                "round": event.round_number,
                "toolName": event.tool_name,
                "success": True,
            }
        )
    elif event.type is ToolLoopEventType.TOOL_CALL_COMPLETED:
        execution = event.execution
        stages.append(
            {
                "stage": "tool_call",
                "round": event.round_number,
                "toolName": execution.tool_name if execution else event.tool_name,
                "success": True,
            }
        )
