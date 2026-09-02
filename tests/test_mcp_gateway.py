from types import SimpleNamespace

import pytest

from app.mcp_gateway import McpGatewayError, call_current_datetime


class FakeClient:
    def __init__(self, tool_names: list[str], *, tool_error: bool = False) -> None:
        self.tool_names = tool_names
        self.tool_error = tool_error
        self.events: list[str] = []

    async def __aenter__(self):
        self.events.append("connect")
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.events.append("disconnect")

    async def list_tools(self):
        self.events.append("tools/list")
        return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in self.tool_names])

    async def call_tool(self, name, arguments):
        self.events.append(f"tools/call:{name}")
        return SimpleNamespace(
            is_error=self.tool_error,
            structured_content={"datetime": "2026-08-04 12:00:00"},
            content=[],
        )


@pytest.mark.asyncio
async def test_gateway_lists_before_calling_tool():
    fake = FakeClient(["get_current_date_time"])

    result = await call_current_datetime(lambda _: fake)

    assert result["success"] is True
    assert result["toolName"] == "get_current_date_time"
    assert result["discoveredTools"] == ["get_current_date_time"]
    assert fake.events == [
        "connect",
        "tools/list",
        "tools/call:get_current_date_time",
        "disconnect",
    ]


@pytest.mark.asyncio
async def test_gateway_stops_when_allowlisted_tool_is_missing():
    fake = FakeClient(["another_tool"])

    with pytest.raises(McpGatewayError) as error:
        await call_current_datetime(lambda _: fake)

    assert error.value.stage == "tool_validation"
    assert "tools/call" not in " ".join(fake.events)

