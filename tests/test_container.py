from app.bootstrap import create_app
from app.container import AppContainer, create_container
from app.core.settings import Settings
from app.integrations.ollama import OllamaDecision
from app.mcp.gateway import McpToolCatalog
from app.skills import SkillRegistry
from tests.fakes import FakeMcpGateway, FakeOllamaGateway


def test_default_containers_do_not_share_skill_registries():
    first = create_container()
    second = create_container()

    assert first is not second
    assert first.skills is not second.skills
    assert callable(first.mcp_gateway_factory)
    assert callable(first.ollama_gateway_factory)


def test_application_uses_the_injected_container():
    fake_mcp = FakeMcpGateway(McpToolCatalog((), ()))
    fake_ollama = FakeOllamaGateway(
        OllamaDecision(
            content="测试回答",
            tool_calls=(),
            assistant_message={"role": "assistant", "content": "测试回答"},
        )
    )
    container = AppContainer(
        settings=Settings(),
        skills=SkillRegistry(),
        mcp_gateway_factory=lambda: fake_mcp,
        ollama_gateway_factory=lambda: fake_ollama,
    )

    application = create_app(container)

    assert application.state.container is container
    assert application.state.container.mcp_gateway_factory() is fake_mcp
    assert application.state.container.ollama_gateway_factory() is fake_ollama
