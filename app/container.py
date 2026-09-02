"""Explicit application dependency container."""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.ports import McpGatewayFactory, OllamaGatewayFactory
from app.core.settings import Settings, settings
from app.integrations.ollama import OllamaGateway
from app.mcp.gateway import McpGateway
from app.skills.registry import SkillRegistry


@dataclass(frozen=True, slots=True)
class AppContainer:
    """Small composition object; intentionally not a service locator."""

    settings: Settings
    skills: SkillRegistry
    mcp_gateway_factory: McpGatewayFactory
    ollama_gateway_factory: OllamaGatewayFactory


def create_container(configuration: Settings = settings) -> AppContainer:
    """Create independent mutable registries with concrete outbound adapters."""

    return AppContainer(
        settings=configuration,
        skills=SkillRegistry(),
        mcp_gateway_factory=McpGateway,
        ollama_gateway_factory=OllamaGateway,
    )
