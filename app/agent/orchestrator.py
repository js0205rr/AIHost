"""Application-layer Ollama and MCP orchestration for the migration MVP."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Mapping
from time import perf_counter
from typing import Any

from app.core.errors import StagedServiceError
from app.core.settings import AGENT_MAX_TOOL_CALLS, OLLAMA_MODEL
from app.integrations.ollama import OllamaGateway, OllamaToolCall
from app.mcp.gateway import McpGateway, McpToolDefinition


class AgentServiceError(StagedServiceError):
    """A safe, client-visible agent orchestration failure."""


McpGatewayFactory = Callable[[], McpGateway]
OllamaGatewayFactory = Callable[[], OllamaGateway]


SYSTEM_PROMPT = (
    "你是 CUBIC AIHost 的工具调用助手。"
    "请根据用户问题和提供的工具说明，决定是否需要调用工具。"
    "只有在工具能够提供必要实时信息时才调用；普通问候或无需实时数据的问题直接回答。"
    "不得编造工具名、参数或工具结果。请始终使用简体中文回答。"
)

FINAL_SYSTEM_PROMPT = "你是一个专业的 AI 助手，请直接回答用户当前的问题。请始终使用简体中文回答。"


def _default_mcp_gateway_factory() -> McpGateway:
    return McpGateway()


def _default_ollama_gateway_factory() -> OllamaGateway:
    return OllamaGateway()


def _to_ollama_tool(tool: McpToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _validate_arguments(tool: McpToolDefinition, call: OllamaToolCall) -> None:
    schema = tool.input_schema
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    if not isinstance(properties, Mapping) or not isinstance(required, list):
        raise AgentServiceError("tool_validation", "MCP 工具参数 Schema 无效")

    unknown = set(call.arguments).difference(properties)
    missing = set(required).difference(call.arguments)
    if unknown:
        raise AgentServiceError("tool_validation", "模型返回了工具未定义的参数")
    if missing:
        raise AgentServiceError("tool_validation", "模型缺少工具必填参数")


def _build_final_messages(
    user_message: str,
    tool_result: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": FINAL_SYSTEM_PROMPT},
    ]
    if tool_result is not None:
        context = json.dumps(tool_result, ensure_ascii=False)
        messages.append(
            {
                "role": "system",
                "content": (
                    "以下是根据用户问题调用工具查询到的数据，请基于这些数据回答用户问题：\n\n"
                    f"{context}"
                ),
            }
        )
    messages.append({"role": "user", "content": user_message})
    return messages


async def stream_agent_events(
    user_message: str,
    mcp_gateway_factory: McpGatewayFactory = _default_mcp_gateway_factory,
    ollama_gateway_factory: OllamaGatewayFactory = _default_ollama_gateway_factory,
) -> AsyncIterator[dict[str, Any]]:
    """Yield production-compatible SSE event payloads for one Agent request."""

    yield {"type": "meta", "model": OLLAMA_MODEL}
    decision_messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    async with mcp_gateway_factory() as mcp, ollama_gateway_factory() as ollama:
        yield {
            "type": "status",
            "stage": "tools_list",
            "content": "正在获取 MCP 工具列表...",
        }
        catalog = await mcp.list_allowed_tools()
        allowed_by_name = {tool.name: tool for tool in catalog.allowed_tools}
        ollama_tools = [_to_ollama_tool(tool) for tool in catalog.allowed_tools]
        if not ollama_tools:
            raise AgentServiceError("tool_validation", "没有可提供给 Ollama 的白名单工具")

        yield {
            "type": "status",
            "stage": "ollama_decision",
            "content": "正在进行 Ollama 工具决策...",
        }
        decision = await ollama.decide(decision_messages, ollama_tools)
        tool_result: dict[str, Any] | None = None

        if not decision.tool_calls:
            yield {"type": "classify", "mode": "general", "label": "通用对话"}
        else:
            if len(decision.tool_calls) > AGENT_MAX_TOOL_CALLS:
                raise AgentServiceError("tool_validation", "当前 MVP 每次只允许一次工具调用")

            call = decision.tool_calls[0]
            tool = allowed_by_name.get(call.name)
            if tool is None:
                raise AgentServiceError("tool_validation", "模型选择了未发现或未授权的工具")

            _validate_arguments(tool, call)
            yield {"type": "classify", "mode": "tool", "label": "工具调用"}
            yield {
                "type": "status",
                "stage": "tool_call",
                "content": f"正在调用：{call.name}...",
            }
            tool_result = await mcp.call_allowed_tool(call.name, call.arguments)
            yield {
                "type": "tool_result",
                "toolName": call.name,
                "displayName": call.name,
                "content": json.dumps(tool_result, ensure_ascii=False),
            }

        yield {
            "type": "status",
            "stage": "ollama_final",
            "content": "正在生成回答...",
        }
        final_messages = _build_final_messages(user_message, tool_result)
        async for content in ollama.stream_final(final_messages):
            yield {"type": "response", "content": content}


async def ask_agent(
    user_message: str,
    mcp_gateway_factory: McpGatewayFactory = _default_mcp_gateway_factory,
    ollama_gateway_factory: OllamaGatewayFactory = _default_ollama_gateway_factory,
) -> dict[str, Any]:
    """Execute tools/list, one model decision and at most one tools/call."""

    started = perf_counter()
    stages: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    async with mcp_gateway_factory() as mcp, ollama_gateway_factory() as ollama:
        catalog = await mcp.list_allowed_tools()
        stages.append({"stage": "tools_list", "success": True})

        allowed_by_name = {tool.name: tool for tool in catalog.allowed_tools}
        ollama_tools = [_to_ollama_tool(tool) for tool in catalog.allowed_tools]
        if not ollama_tools:
            raise AgentServiceError("tool_validation", "没有可提供给 Ollama 的白名单工具")

        decision = await ollama.decide(messages, ollama_tools)
        stages.append({"stage": "ollama_decision", "success": True})

        if not decision.tool_calls:
            return {
                "success": True,
                "mode": "general",
                "model": OLLAMA_MODEL,
                "discoveredTools": list(catalog.discovered_tools),
                "advertisedTools": list(allowed_by_name),
                "selectedTool": None,
                "toolArguments": None,
                "toolResult": None,
                "answer": decision.content,
                "stages": stages,
                "elapsedMs": round((perf_counter() - started) * 1000, 2),
            }

        if len(decision.tool_calls) > AGENT_MAX_TOOL_CALLS:
            raise AgentServiceError("tool_validation", "当前 MVP 每次只允许一次工具调用")

        call = decision.tool_calls[0]
        tool = allowed_by_name.get(call.name)
        if tool is None:
            raise AgentServiceError("tool_validation", "模型选择了未发现或未授权的工具")

        _validate_arguments(tool, call)
        stages.append({"stage": "tool_validation", "success": True})

        tool_result = await mcp.call_allowed_tool(call.name, call.arguments)
        stages.append({"stage": "tool_call", "success": True})

        messages.append(decision.assistant_message)
        messages.append(
            {
                "role": "tool",
                "tool_name": call.name,
                "content": json.dumps(tool_result, ensure_ascii=False),
            }
        )
        answer = await ollama.generate_final(messages)
        stages.append({"stage": "ollama_final", "success": True})

    return {
        "success": True,
        "mode": "tool",
        "model": OLLAMA_MODEL,
        "discoveredTools": list(catalog.discovered_tools),
        "advertisedTools": list(allowed_by_name),
        "selectedTool": call.name,
        "toolArguments": call.arguments,
        "toolResult": tool_result,
        "answer": answer,
        "stages": stages,
        "elapsedMs": round((perf_counter() - started) * 1000, 2),
    }
