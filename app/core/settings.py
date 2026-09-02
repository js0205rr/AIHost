"""Typed local settings for the migration MVP.

Environment-backed production configuration is intentionally deferred.  The
legacy constant aliases keep the current runtime and tests stable while new
modules depend on a single immutable settings object.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    aihost_host: str = "127.0.0.1"
    aihost_port: int = 18080

    mcp_server_url: str = "http://127.0.0.1:18081/mcp"
    mcp_tool_name: str = "get_current_date_time"
    mcp_tool_allowlist: frozenset[str] = frozenset({"get_current_date_time"})
    mcp_read_timeout_seconds: float = 10.0

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:0.6b"
    ollama_request_timeout_seconds: float = 120.0
    ollama_keep_alive: str = "5m"
    ollama_decision_num_predict: int = 256
    ollama_answer_num_predict: int = 512

    agent_max_tool_calls: int = 1


settings = Settings()

# Compatibility aliases for the existing MVP modules and external imports.
AIHOST_HOST = settings.aihost_host
AIHOST_PORT = settings.aihost_port
MCP_SERVER_URL = settings.mcp_server_url
MCP_TOOL_NAME = settings.mcp_tool_name
MCP_TOOL_ALLOWLIST = settings.mcp_tool_allowlist
MCP_READ_TIMEOUT_SECONDS = settings.mcp_read_timeout_seconds
OLLAMA_HOST = settings.ollama_host
OLLAMA_MODEL = settings.ollama_model
OLLAMA_REQUEST_TIMEOUT_SECONDS = settings.ollama_request_timeout_seconds
OLLAMA_KEEP_ALIVE = settings.ollama_keep_alive
OLLAMA_DECISION_NUM_PREDICT = settings.ollama_decision_num_predict
OLLAMA_ANSWER_NUM_PREDICT = settings.ollama_answer_num_predict
AGENT_MAX_TOOL_CALLS = settings.agent_max_tool_calls
