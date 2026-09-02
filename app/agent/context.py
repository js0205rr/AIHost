"""Request-scoped models used by Agent and Skill orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping
from uuid import uuid4


MessageRole = Literal["system", "user", "assistant", "tool"]


def _empty_metadata() -> Mapping[str, Any]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    """One validated message in an internal conversation history."""

    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("不支持的对话角色")
        if not self.content or not self.content.strip():
            raise ValueError("对话内容不能为空")


@dataclass(frozen=True, slots=True)
class UserContext:
    """Authenticated user data available to application services."""

    user_id: str
    display_name: str = ""
    union_id: str | None = None
    claims: Mapping[str, Any] = field(default_factory=_empty_metadata)

    def __post_init__(self) -> None:
        if not self.user_id or not self.user_id.strip():
            raise ValueError("user_id 不能为空")
        object.__setattr__(self, "user_id", self.user_id.strip())
        object.__setattr__(self, "display_name", self.display_name.strip())
        object.__setattr__(self, "claims", MappingProxyType(dict(self.claims)))


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Transport-neutral input shared by Agent and Skill handlers.

    Python task cancellation is propagated by ``asyncio`` and therefore is not
    represented as a mutable cancellation flag in this model.
    """

    message: str
    history: tuple[ConversationMessage, ...] = ()
    locale: str = "zh-CN"
    user: UserContext | None = None
    request_id: str = field(default_factory=lambda: uuid4().hex)
    metadata: Mapping[str, Any] = field(default_factory=_empty_metadata)

    def __post_init__(self) -> None:
        normalized_message = self.message.strip()
        if not normalized_message:
            raise ValueError("message 不能为空")

        normalized_locale = (self.locale or "zh-CN").strip() or "zh-CN"
        normalized_request_id = self.request_id.strip()
        if not normalized_request_id:
            raise ValueError("request_id 不能为空")

        object.__setattr__(self, "message", normalized_message)
        object.__setattr__(self, "history", tuple(self.history))
        object.__setattr__(self, "locale", normalized_locale)
        object.__setattr__(self, "request_id", normalized_request_id)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def is_english(self) -> bool:
        return self.locale.casefold().startswith("en")
