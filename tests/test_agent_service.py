import pytest

from app.agent.context import AgentContext, ConversationMessage
from app.agent_service import AgentServiceError, ask_agent, stream_agent_events
from app.mcp_gateway import McpToolCatalog, McpToolDefinition
from app.ollama_gateway import OllamaDecision, OllamaToolCall


TIME_TOOL = McpToolDefinition(
    name="get_current_date_time",
    description="返回服务器当前日期和时间。",
    input_schema={"type": "object", "properties": {}},
)


class FakeMcpGateway:
    def __init__(self) -> None:
        self.called = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def list_allowed_tools(self):
        return McpToolCatalog(
            discovered_tools=(TIME_TOOL.name,),
            allowed_tools=(TIME_TOOL,),
        )

    async def call_allowed_tool(self, name, arguments):
        self.called = True
        assert name == TIME_TOOL.name
        assert arguments == {}
        return {"datetime": "2026-08-06 15:30:00"}


class FakeOllamaGateway:
    def __init__(self, *decisions: OllamaDecision) -> None:
        self.decisions = decisions
        self.decision_index = 0
        self.decision_messages = []
        self.final_messages = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def decide(self, messages, tools):
        assert tools[0]["function"]["name"] == TIME_TOOL.name
        self.decision_messages.append(list(messages))
        decision = self.decisions[self.decision_index]
        self.decision_index += 1
        return decision

    async def generate_final(self, messages):
        self.final_messages = messages
        return "当前时间是 2026-08-06 15:30:00。"

    async def stream_final(self, messages):
        self.final_messages = messages
        for content in ("当前时间是 ", "2026-08-06 15:30:00。"):
            yield content


async def test_agent_returns_first_model_answer_when_no_tool_is_needed():
    mcp = FakeMcpGateway()
    ollama = FakeOllamaGateway(
        OllamaDecision(
            content="你好！",
            tool_calls=(),
            assistant_message={"role": "assistant", "content": "你好！"},
        )
    )

    result = await ask_agent("你好", lambda: mcp, lambda: ollama)

    assert result["mode"] == "general"
    assert result["answer"] == "你好！"
    assert mcp.called is False


async def test_agent_accepts_context_and_passes_history_to_model():
    mcp = FakeMcpGateway()
    ollama = FakeOllamaGateway(
        OllamaDecision(
            content="结合历史回答",
            tool_calls=(),
            assistant_message={"role": "assistant", "content": "结合历史回答"},
        )
    )
    context = AgentContext(
        message="继续",
        history=(
            ConversationMessage(role="user", content="上一问"),
            ConversationMessage(role="assistant", content="上一答"),
        ),
        request_id="request-history",
    )

    result = await ask_agent(context, lambda: mcp, lambda: ollama)

    assert result["answer"] == "结合历史回答"
    assert [message["content"] for message in ollama.decision_messages[0][1:]] == [
        "上一问",
        "上一答",
        "继续",
    ]


async def test_agent_calls_allowlisted_tool_and_generates_final_answer():
    mcp = FakeMcpGateway()
    ollama = FakeOllamaGateway(
        OllamaDecision(
            content="",
            tool_calls=(OllamaToolCall(TIME_TOOL.name, {}),),
            assistant_message={
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": TIME_TOOL.name, "arguments": {}}}
                ],
            },
        ),
        OllamaDecision(
            content="工具调用完成",
            tool_calls=(),
            assistant_message={"role": "assistant", "content": "工具调用完成"},
        ),
    )

    result = await ask_agent("现在几点？", lambda: mcp, lambda: ollama)

    assert result["mode"] == "tool"
    assert result["selectedTool"] == TIME_TOOL.name
    assert result["toolResult"]["datetime"] == "2026-08-06 15:30:00"
    assert result["answer"].startswith("当前时间")
    assert mcp.called is True
    assert ollama.final_messages[-1]["role"] == "tool"


async def test_agent_rejects_model_selected_tool_outside_allowlist():
    mcp = FakeMcpGateway()
    ollama = FakeOllamaGateway(
        OllamaDecision(
            content="",
            tool_calls=(OllamaToolCall("unapproved_tool", {}),),
            assistant_message={"role": "assistant", "tool_calls": []},
        )
    )

    with pytest.raises(AgentServiceError) as error:
        await ask_agent("执行未授权工具", lambda: mcp, lambda: ollama)

    assert error.value.stage == "tool_validation"
    assert mcp.called is False


async def test_stream_agent_emits_general_classification_and_response_chunks():
    mcp = FakeMcpGateway()
    ollama = FakeOllamaGateway(
        OllamaDecision(
            content="普通回答决策完成",
            tool_calls=(),
            assistant_message={"role": "assistant", "content": "普通回答决策完成"},
        )
    )

    events = [event async for event in stream_agent_events("你好", lambda: mcp, lambda: ollama)]

    assert [event["type"] for event in events] == [
        "meta",
        "status",
        "status",
        "classify",
        "status",
        "response",
        "response",
    ]
    assert events[3]["mode"] == "general"
    assert "".join(event["content"] for event in events if event["type"] == "response").startswith("当前时间")
    assert mcp.called is False


async def test_stream_agent_emits_tool_result_before_response_chunks():
    mcp = FakeMcpGateway()
    ollama = FakeOllamaGateway(
        OllamaDecision(
            content="",
            tool_calls=(OllamaToolCall(TIME_TOOL.name, {}),),
            assistant_message={
                "role": "assistant",
                "tool_calls": [{"function": {"name": TIME_TOOL.name, "arguments": {}}}],
            },
        ),
        OllamaDecision(
            content="工具调用完成",
            tool_calls=(),
            assistant_message={"role": "assistant", "content": "工具调用完成"},
        ),
    )

    events = [
        event
        async for event in stream_agent_events("现在几点？", lambda: mcp, lambda: ollama)
    ]
    types = [event["type"] for event in events]

    assert "tool_result" in types
    assert types.index("tool_result") < types.index("response")
    assert next(event for event in events if event["type"] == "classify")["mode"] == "tool"
    assert mcp.called is True
    assert any(
        message["role"] == "tool" and "datetime" in message["content"]
        for message in ollama.final_messages
    )
    assert ollama.decision_index == 2
