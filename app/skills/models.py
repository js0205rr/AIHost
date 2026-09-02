"""Transport-neutral Skill definitions and result models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from app.agent.context import AgentContext


class SkillResultType(str, Enum):
    STATUS = "status"
    TEXT = "text"
    TOOL_RESULT = "tool_result"
    TABLE = "table"
    SOURCES = "sources"
    ERROR = "error"
    COMPLETED = "completed"


def _empty_metadata() -> Mapping[str, Any]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class SkillResult:
    """One internal result emitted by a Skill handler."""

    type: SkillResultType
    content: Any = None
    name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=_empty_metadata)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @classmethod
    def status(cls, content: str) -> SkillResult:
        return cls(SkillResultType.STATUS, content=content)

    @classmethod
    def text(cls, content: str) -> SkillResult:
        return cls(SkillResultType.TEXT, content=content)

    @classmethod
    def tool_result(cls, name: str, content: Any) -> SkillResult:
        return cls(SkillResultType.TOOL_RESULT, content=content, name=name)

    @classmethod
    def table(cls, content: Any, *, name: str | None = None) -> SkillResult:
        return cls(SkillResultType.TABLE, content=content, name=name)

    @classmethod
    def sources(cls, content: Any) -> SkillResult:
        return cls(SkillResultType.SOURCES, content=content)

    @classmethod
    def error(
        cls,
        content: str,
        *,
        code: str | None = None,
        retryable: bool = False,
    ) -> SkillResult:
        return cls(
            SkillResultType.ERROR,
            content=content,
            metadata={"code": code, "retryable": retryable},
        )

    @classmethod
    def completed(cls) -> SkillResult:
        return cls(SkillResultType.COMPLETED)


SkillHandler = Callable[[AgentContext], AsyncIterator[SkillResult]]


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """Metadata and handler for one application-level capability."""

    skill_id: str
    command_name: str
    display_name: str
    description: str
    handler: SkillHandler
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized_id = self.skill_id.strip()
        normalized_command = _normalize_command(self.command_name)
        normalized_display_name = self.display_name.strip()
        normalized_description = self.description.strip()
        normalized_aliases = tuple(_normalize_command(alias) for alias in self.aliases)

        if not normalized_id:
            raise ValueError("skill_id 不能为空")
        if not normalized_display_name:
            raise ValueError("display_name 不能为空")
        if not normalized_description:
            raise ValueError("description 不能为空")

        object.__setattr__(self, "skill_id", normalized_id)
        object.__setattr__(self, "command_name", normalized_command)
        object.__setattr__(self, "display_name", normalized_display_name)
        object.__setattr__(self, "description", normalized_description)
        object.__setattr__(self, "aliases", normalized_aliases)

    @property
    def commands(self) -> tuple[str, ...]:
        return (self.command_name, *self.aliases)


@dataclass(frozen=True, slots=True)
class SkillMatch:
    definition: SkillDefinition
    arguments: str


def _normalize_command(command: str) -> str:
    normalized = command.strip().removeprefix("/").strip()
    if not normalized or any(character.isspace() for character in normalized):
        raise ValueError("Skill 命令不能为空或包含空白字符")
    return normalized
