from fastapi.testclient import TestClient

from app import main
from app.mcp_gateway import McpGatewayError
from app.web import routes


client = TestClient(main.app)


def test_mvp_page_is_available():
    response = client.get("/mvp")

    assert response.status_code == 200
    assert "Python AIHost 当前能力验收" in response.text


def test_fixed_endpoint_returns_gateway_result(monkeypatch):
    async def fake_call():
        return {
            "success": True,
            "toolName": "get_current_date_time",
            "discoveredTools": ["get_current_date_time"],
            "result": {"datetime": "2026-08-04 12:00:00"},
            "elapsedMs": 1.25,
        }

    monkeypatch.setattr(routes, "call_current_datetime", fake_call)
    response = client.post("/api/mvp/tools/get_current_date_time/call", json={})

    assert response.status_code == 200
    assert response.json()["toolName"] == "get_current_date_time"


def test_fixed_endpoint_reports_failure_stage(monkeypatch):
    async def fake_call():
        raise McpGatewayError("tools_list", "无法连接 MCP Server")

    monkeypatch.setattr(routes, "call_current_datetime", fake_call)
    response = client.post("/api/mvp/tools/get_current_date_time/call", json={})

    assert response.status_code == 502
    assert response.json() == {
        "success": False,
        "stage": "tools_list",
        "message": "无法连接 MCP Server",
    }


def test_agent_endpoint_returns_general_answer(monkeypatch):
    async def fake_ask(message, mcp_gateway_factory, ollama_gateway_factory):
        assert message == "你好"
        assert callable(mcp_gateway_factory)
        assert callable(ollama_gateway_factory)
        return {
            "success": True,
            "mode": "general",
            "model": "qwen3:0.6b",
            "answer": "你好！",
            "elapsedMs": 2.5,
        }

    monkeypatch.setattr(routes, "ask_agent", fake_ask)
    response = client.post("/api/mvp/agent/ask", json={"message": " 你好 "})

    assert response.status_code == 200
    assert response.json()["mode"] == "general"


def test_agent_endpoint_rejects_blank_message():
    response = client.post("/api/mvp/agent/ask", json={"message": "   "})

    assert response.status_code == 422


def test_agent_stream_endpoint_uses_sse_protocol(monkeypatch):
    async def fake_stream(message, mcp_gateway_factory, ollama_gateway_factory):
        assert message == "你好"
        assert callable(mcp_gateway_factory)
        assert callable(ollama_gateway_factory)
        yield {"type": "meta", "model": "qwen3:0.6b"}
        yield {"type": "classify", "mode": "general", "label": "通用对话"}
        yield {"type": "response", "content": "你"}
        yield {"type": "response", "content": "好"}

    monkeypatch.setattr(routes, "stream_agent_events", fake_stream)
    response = client.post("/api/mvp/agent/ask-stream", json={"message": "你好"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"type":"response","content":"你"}' in response.text
    assert response.text.endswith("data: [DONE]\n\n")
