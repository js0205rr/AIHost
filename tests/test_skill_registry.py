import pytest

from app.agent.context import AgentContext
from app.skills import (
    SkillDefinition,
    SkillRegistrationError,
    SkillRegistry,
    SkillResult,
    SkillResultType,
)


async def sample_handler(context: AgentContext):
    yield SkillResult.status(f"处理：{context.message}")
    yield SkillResult.text("完成")
    yield SkillResult.completed()


def make_skill(**overrides):
    values = {
        "skill_id": "order-details",
        "command_name": "order-details",
        "display_name": "订单详情查询",
        "description": "查询并整理订单详情。",
        "handler": sample_handler,
        "aliases": ("订单详情",),
    }
    values.update(overrides)
    return SkillDefinition(**values)


def test_registry_matches_primary_command_and_alias_case_insensitively():
    registry = SkillRegistry()
    definition = registry.register(make_skill())

    primary = registry.match("/ORDER-DETAILS  A-100 ")
    alias = registry.match("/订单详情 A-200")

    assert primary is not None
    assert primary.definition is definition
    assert primary.arguments == "A-100"
    assert alias is not None
    assert alias.arguments == "A-200"
    assert registry.list_skills() == (definition,)


def test_registry_returns_none_for_plain_or_unknown_messages():
    registry = SkillRegistry()
    registry.register(make_skill())

    assert registry.match("查询订单") is None
    assert registry.match("/unknown value") is None
    assert registry.match("/") is None


def test_registry_rejects_duplicate_commands_without_partial_registration():
    registry = SkillRegistry()
    original = registry.register(make_skill())

    with pytest.raises(SkillRegistrationError, match="命令已注册"):
        registry.register(
            make_skill(
                skill_id="another-skill",
                command_name="ORDER-DETAILS",
                aliases=(),
            )
        )

    assert registry.list_skills() == (original,)
    assert registry.get("another-skill") is None


async def test_skill_handler_emits_transport_neutral_results():
    definition = make_skill()
    context = AgentContext(message="查询 A-100")

    results = [result async for result in definition.handler(context)]

    assert [result.type for result in results] == [
        SkillResultType.STATUS,
        SkillResultType.TEXT,
        SkillResultType.COMPLETED,
    ]
    assert results[0].content == "处理：查询 A-100"


def test_error_result_contains_machine_readable_metadata():
    result = SkillResult.error("MCP 调用失败", code="mcp_error", retryable=True)

    assert result.type is SkillResultType.ERROR
    assert result.metadata == {"code": "mcp_error", "retryable": True}
