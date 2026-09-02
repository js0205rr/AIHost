import pytest

from app.agent.context import AgentContext, ConversationMessage
from app.agent.errors import AgentLoopLimitError
from app.agent.tool_loop import ToolLoopEventType, iterate_tool_loop
from app.integrations.ollama import OllamaDecision, OllamaToolCall
from app.mcp.gateway import McpToolCatalog, McpToolDefinition
from tests.fakes import FakeMcpGateway, FakeOllamaGateway


TIME_TOOL = McpToolDefinition(
    name="get_current_date_time",
    description="获取时间",
    input_schema={"type": "object", "properties": {}},
)
ORDER_TOOL = McpToolDefinition(
    name="query_orders",
    description="查询订单",
    input_schema={
        "type": "object",
        "properties": {"order_id": {"type": "string", "minLength": 1}},
        "required": ["order_id"],
    },
)


def decision(*calls: OllamaToolCall, content: str = "") -> OllamaDecision:
    return OllamaDecision(
        content=content,
        tool_calls=tuple(calls),
        assistant_message={
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {"function": {"name": call.name, "arguments": call.arguments}}
                for call in calls
            ],
        },
    )


async def collect_loop(mcp, ollama, *, max_rounds=5, max_tool_calls=5):
    return [
        event
        async for event in iterate_tool_loop(
            context=AgentContext(
                message="查询订单并告诉我时间",
                history=(
                    ConversationMessage(role="user", content="前一条问题"),
                    ConversationMessage(role="assistant", content="前一条回答"),
                ),
                request_id="request-tool-loop",
            ),
            system_prompt="测试",
            mcp=mcp,
            ollama=ollama,
            max_rounds=max_rounds,
            max_tool_calls=max_tool_calls,
        )
    ]


async def test_loop_supports_multiple_tools_and_follow_up_rounds():
    catalog = McpToolCatalog(
        discovered_tools=(TIME_TOOL.name, ORDER_TOOL.name),
        allowed_tools=(TIME_TOOL, ORDER_TOOL),
    )
    mcp = FakeMcpGateway(
        catalog,
        results={
            TIME_TOOL.name: {"datetime": "2026-09-02 10:00:00"},
            ORDER_TOOL.name: {"order_id": "A-100"},
        },
    )
    ollama = FakeOllamaGateway(
        decision(
            OllamaToolCall(TIME_TOOL.name, {}),
            OllamaToolCall(ORDER_TOOL.name, {"order_id": "A-100"}),
        ),
        additional_decisions=(decision(content="工具已齐全"),),
    )

    events = await collect_loop(mcp, ollama)
    outcome = events[-1].outcome

    assert events[-1].type is ToolLoopEventType.COMPLETED
    assert outcome is not None
    assert outcome.mode == "tool"
    assert [execution.tool_name for execution in outcome.executions] == [
        TIME_TOOL.name,
        ORDER_TOOL.name,
    ]
    assert mcp.calls == [
        (TIME_TOOL.name, {}),
        (ORDER_TOOL.name, {"order_id": "A-100"}),
    ]
    assert [message["role"] for message in outcome.messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "tool",
        "tool",
    ]
    assert all(
        execution.request_id == "request-tool-loop"
        for execution in outcome.executions
    )
    assert ollama.decision_calls == 2


async def test_loop_rejects_tool_call_count_before_execution():
    catalog = McpToolCatalog(
        discovered_tools=(TIME_TOOL.name, ORDER_TOOL.name),
        allowed_tools=(TIME_TOOL, ORDER_TOOL),
    )
    mcp = FakeMcpGateway(catalog)
    ollama = FakeOllamaGateway(
        decision(
            OllamaToolCall(TIME_TOOL.name, {}),
            OllamaToolCall(ORDER_TOOL.name, {"order_id": "A-100"}),
        )
    )

    with pytest.raises(AgentLoopLimitError, match="调用总数超过限制") as error:
        await collect_loop(mcp, ollama, max_tool_calls=1)

    assert error.value.code == "tool_loop_limit"
    assert mcp.calls == []


async def test_loop_stops_when_model_never_finishes_tool_calls():
    catalog = McpToolCatalog(
        discovered_tools=(TIME_TOOL.name,),
        allowed_tools=(TIME_TOOL,),
    )
    mcp = FakeMcpGateway(
        catalog,
        results={TIME_TOOL.name: {"datetime": "2026-09-02 10:00:00"}},
    )
    repeated_call = decision(OllamaToolCall(TIME_TOOL.name, {}))
    ollama = FakeOllamaGateway(
        repeated_call,
        additional_decisions=(repeated_call,),
    )

    with pytest.raises(AgentLoopLimitError, match="最大工具轮次"):
        await collect_loop(mcp, ollama, max_rounds=2)

    assert len(mcp.calls) == 2
