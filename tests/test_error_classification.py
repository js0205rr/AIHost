from app.agent.errors import AgentLoopLimitError, ToolArgumentsError, ToolSchemaError
from app.integrations.ollama import OllamaGatewayError
from app.mcp.gateway import McpGatewayError


def test_agent_errors_have_stable_codes():
    assert ToolArgumentsError("参数错误").code == "invalid_tool_arguments"
    assert ToolSchemaError().code == "invalid_tool_schema"
    assert AgentLoopLimitError("超过限制").code == "tool_loop_limit"


def test_upstream_errors_are_namespaced_and_retry_is_explicit():
    mcp_error = McpGatewayError("tools_list", "连接失败", retryable=True)
    ollama_error = OllamaGatewayError("ollama_connect", "连接失败", retryable=True)

    assert mcp_error.code == "mcp_tools_list"
    assert mcp_error.retryable is True
    assert ollama_error.code == "ollama_connect"
    assert ollama_error.retryable is True
