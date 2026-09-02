"""Reusable outbound adapter test doubles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.integrations.ollama import OllamaDecision
from app.mcp.gateway import McpToolCatalog


@dataclass
class FakeMcpGateway:
    catalog: McpToolCatalog
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def __aenter__(self) -> FakeMcpGateway:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None

    async def list_allowed_tools(self) -> McpToolCatalog:
        return self.catalog

    async def call_allowed_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_arguments = dict(arguments or {})
        self.calls.append((tool_name, normalized_arguments))
        return dict(self.results[tool_name])


@dataclass
class FakeOllamaGateway:
    decision: OllamaDecision
    additional_decisions: tuple[OllamaDecision, ...] = ()
    final_answer: str = ""
    stream_chunks: tuple[str, ...] = ()
    decision_calls: int = 0
    final_messages: list[dict[str, Any]] | None = None

    async def __aenter__(self) -> FakeOllamaGateway:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None

    async def decide(self, messages, tools) -> OllamaDecision:
        decisions = (self.decision, *self.additional_decisions)
        if self.decision_calls >= len(decisions):
            raise AssertionError("FakeOllamaGateway 没有更多预设决策")
        decision = decisions[self.decision_calls]
        self.decision_calls += 1
        return decision

    async def generate_final(self, messages) -> str:
        self.final_messages = list(messages)
        return self.final_answer

    async def stream_final(self, messages):
        self.final_messages = list(messages)
        for chunk in self.stream_chunks:
            yield chunk
