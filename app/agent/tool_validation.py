"""JSON Schema validation for model-selected MCP tool arguments."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from app.agent.errors import ToolArgumentsError, ToolSchemaError
from app.mcp.gateway import McpToolDefinition


_VALIDATION_MESSAGES = {
    "required": "缺少必填参数",
    "additionalProperties": "包含未定义参数",
    "type": "参数类型不正确",
    "enum": "参数值不在允许范围",
    "const": "参数值不符合固定要求",
    "minimum": "参数小于允许的最小值",
    "maximum": "参数大于允许的最大值",
    "exclusiveMinimum": "参数未满足最小值限制",
    "exclusiveMaximum": "参数未满足最大值限制",
    "minLength": "字符串长度不足",
    "maxLength": "字符串长度超过限制",
    "pattern": "字符串格式不正确",
    "minItems": "数组元素数量不足",
    "maxItems": "数组元素数量超过限制",
    "uniqueItems": "数组包含重复元素",
    "oneOf": "参数未匹配唯一允许结构",
    "anyOf": "参数未匹配任一允许结构",
    "allOf": "参数未满足全部结构要求",
}


def validate_tool_arguments(
    tool: McpToolDefinition,
    arguments: Mapping[str, Any],
) -> None:
    """Validate one call and reject undeclared top-level arguments."""

    schema = dict(tool.input_schema)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ToolSchemaError() from exc

    errors = sorted(
        Draft202012Validator(schema).iter_errors(dict(arguments)),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return

    error = errors[0]
    path = ".".join(str(part) for part in error.absolute_path) or "参数对象"
    reason = _VALIDATION_MESSAGES.get(error.validator, "参数不符合工具 Schema")
    raise ToolArgumentsError(f"{path}：{reason}")
