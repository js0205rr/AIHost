"""Deterministic in-process registry for application Skills."""

from __future__ import annotations

from app.skills.models import SkillDefinition, SkillMatch


class SkillRegistrationError(ValueError):
    """Raised when Skill identifiers or commands conflict."""


class SkillRegistry:
    """Register and match Skills without coupling them to HTTP or SSE."""

    def __init__(self) -> None:
        self._by_id: dict[str, SkillDefinition] = {}
        self._by_command: dict[str, SkillDefinition] = {}

    def register(self, definition: SkillDefinition) -> SkillDefinition:
        skill_key = definition.skill_id.casefold()
        command_keys = tuple(command.casefold() for command in definition.commands)

        if skill_key in self._by_id:
            raise SkillRegistrationError(f"Skill ID 已注册：{definition.skill_id}")
        if len(set(command_keys)) != len(command_keys):
            raise SkillRegistrationError(f"Skill 内存在重复命令：{definition.skill_id}")

        conflicts = [
            command
            for command, key in zip(definition.commands, command_keys, strict=True)
            if key in self._by_command
        ]
        if conflicts:
            raise SkillRegistrationError(f"Skill 命令已注册：{conflicts[0]}")

        self._by_id[skill_key] = definition
        for command_key in command_keys:
            self._by_command[command_key] = definition
        return definition

    def get(self, skill_id: str) -> SkillDefinition | None:
        return self._by_id.get(skill_id.strip().casefold())

    def list_skills(self) -> tuple[SkillDefinition, ...]:
        return tuple(self._by_id.values())

    def match(self, message: str) -> SkillMatch | None:
        if not message or not message.startswith("/"):
            return None

        body = message[1:].lstrip()
        if not body:
            return None

        parts = body.split(maxsplit=1)
        definition = self._by_command.get(parts[0].casefold())
        if definition is None:
            return None

        arguments = parts[1].strip() if len(parts) == 2 else ""
        return SkillMatch(definition=definition, arguments=arguments)
