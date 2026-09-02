import pytest

from app.agent.errors import ToolArgumentsError, ToolSchemaError
from app.agent.tool_validation import validate_tool_arguments
from app.mcp.gateway import McpToolDefinition


ORDER_TOOL = McpToolDefinition(
    name="query_orders",
    description="查询订单",
    input_schema={
        "type": "object",
        "properties": {
            "order_ids": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
                "maxItems": 20,
                "uniqueItems": True,
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            "status": {"type": "string", "enum": ["open", "closed"]},
        },
        "required": ["order_ids"],
    },
)


def test_validator_accepts_arguments_matching_full_schema():
    validate_tool_arguments(
        ORDER_TOOL,
        {"order_ids": ["A-100", "A-101"], "limit": 20, "status": "open"},
    )


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"limit": 20}, "缺少必填参数"),
        ({"order_ids": ["A-100"], "unknown": True}, "包含未定义参数"),
        ({"order_ids": [10]}, "参数类型不正确"),
        ({"order_ids": ["A-100"], "limit": 0}, "小于允许的最小值"),
        ({"order_ids": ["A-100"], "status": "invalid"}, "不在允许范围"),
    ],
)
def test_validator_classifies_invalid_arguments(arguments, expected):
    with pytest.raises(ToolArgumentsError, match=expected) as error:
        validate_tool_arguments(ORDER_TOOL, arguments)

    assert error.value.stage == "tool_validation"
    assert error.value.code == "invalid_tool_arguments"
    assert error.value.retryable is False


def test_validator_classifies_invalid_mcp_schema():
    tool = McpToolDefinition(
        name="broken",
        description="无效工具",
        input_schema={"type": "unsupported"},
    )

    with pytest.raises(ToolSchemaError) as error:
        validate_tool_arguments(tool, {})

    assert error.value.stage == "tool_schema"
    assert error.value.code == "invalid_tool_schema"
