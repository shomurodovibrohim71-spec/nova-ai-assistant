import logging
from typing import Iterable

from .base import Skill

log = logging.getLogger(__name__)


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"skill {skill.name!r} already registered")
        self._skills[skill.name] = skill
        log.info("registered skill: %s", skill.name)

    def all(self) -> Iterable[Skill]:
        return self._skills.values()

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)
