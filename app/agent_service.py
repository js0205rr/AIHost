"""Compatibility exports for the original MVP agent module."""

from app.agent.orchestrator import (
    AgentServiceError,
    FINAL_SYSTEM_PROMPT,
    McpGatewayFactory,
    OllamaGatewayFactory,
    SYSTEM_PROMPT,
    ask_agent,
    stream_agent_events,
)

__all__ = [
    "AgentServiceError",
    "FINAL_SYSTEM_PROMPT",
    "McpGatewayFactory",
    "OllamaGatewayFactory",
    "SYSTEM_PROMPT",
    "ask_agent",
    "stream_agent_events",
]

