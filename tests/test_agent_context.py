from types import MappingProxyType

import pytest

from app.agent.context import AgentContext, ConversationMessage, UserContext


def test_agent_context_normalizes_request_data():
    history = [ConversationMessage(role="user", content="前一条消息")]
    user = UserContext(
        user_id=" 1001 ",
        display_name=" Gary ",
        claims={"department": "IT"},
    )

    context = AgentContext(
        message="  查询订单  ",
        history=history,
        locale=" en-US ",
        user=user,
        request_id=" request-1 ",
        metadata={"source": "test"},
    )

    assert context.message == "查询订单"
    assert context.history == tuple(history)
    assert context.is_english is True
    assert context.user.user_id == "1001"
    assert context.request_id == "request-1"
    assert isinstance(context.metadata, MappingProxyType)


def test_agent_context_rejects_blank_message():
    with pytest.raises(ValueError, match="message 不能为空"):
        AgentContext(message="   ")


def test_conversation_message_rejects_invalid_role():
    with pytest.raises(ValueError, match="不支持的对话角色"):
        ConversationMessage(role="invalid", content="内容")  # type: ignore[arg-type]


def test_user_claims_are_copied_and_read_only():
    source = {"role": "admin"}
    user = UserContext(user_id="1001", claims=source)
    source["role"] = "changed"

    assert user.claims["role"] == "admin"
    with pytest.raises(TypeError):
        user.claims["role"] = "changed"  # type: ignore[index]
