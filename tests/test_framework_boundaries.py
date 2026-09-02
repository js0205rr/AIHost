from app.agent.orchestrator import ask_agent as canonical_ask_agent
from app.agent_service import ask_agent as compatibility_ask_agent
from app.bootstrap import create_app
from app.mcp.gateway import McpGateway as CanonicalMcpGateway
from app.mcp_gateway import McpGateway as CompatibilityMcpGateway


def test_legacy_imports_resolve_to_canonical_modules():
    assert compatibility_ask_agent is canonical_ask_agent
    assert CompatibilityMcpGateway is CanonicalMcpGateway


def test_application_factory_builds_an_isolated_app():
    first = create_app()
    second = create_app()

    assert first is not second
    assert "/api/mvp/agent/ask" in first.openapi()["paths"]
