from app.agent.orchestrator import ask_agent
from app.integrations.ollama import OllamaDecision, OllamaToolCall
from app.mcp.gateway import McpToolCatalog, McpToolDefinition
from tests.fakes import FakeMcpGateway, FakeOllamaGateway


async def test_agent_returns_legacy_fields_and_complete_multi_tool_trace():
    first_tool = McpToolDefinition(
        name="first_tool",
        description="第一个工具",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
        },
    )
    second_tool = McpToolDefinition(
        name="second_tool",
        description="第二个工具",
        input_schema={"type": "object", "properties": {}},
    )
    catalog = McpToolCatalog(
        discovered_tools=(first_tool.name, second_tool.name),
        allowed_tools=(first_tool, second_tool),
    )
    mcp = FakeMcpGateway(
        catalog,
        results={
            first_tool.name: {"first": 1},
            second_tool.name: {"second": 2},
        },
    )
    tool_decision = OllamaDecision(
        content="",
        tool_calls=(
            OllamaToolCall(first_tool.name, {"value": 1}),
            OllamaToolCall(second_tool.name, {}),
        ),
        assistant_message={
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": first_tool.name, "arguments": {"value": 1}}},
                {"function": {"name": second_tool.name, "arguments": {}}},
            ],
        },
    )
    terminal_decision = OllamaDecision(
        content="工具调用结束",
        tool_calls=(),
        assistant_message={"role": "assistant", "content": "工具调用结束"},
    )
    ollama = FakeOllamaGateway(
        tool_decision,
        additional_decisions=(terminal_decision,),
        final_answer="最终回答",
    )

    result = await ask_agent("执行两个工具", lambda: mcp, lambda: ollama)

    assert result["mode"] == "tool"
    assert result["selectedTool"] == first_tool.name
    assert result["toolArguments"] == {"value": 1}
    assert result["toolResult"] == {"first": 1}
    assert [call["toolName"] for call in result["toolCalls"]] == [
        first_tool.name,
        second_tool.name,
    ]
    assert result["answer"] == "最终回答"
    assert [stage["round"] for stage in result["stages"] if "round" in stage] == [
        1,
        1,
        1,
        1,
        1,
        2,
    ]
