"""Types owned by the deterministic guest-check registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

CheckRisk = Literal["read_only", "mutating"]
CommandBuilder = Callable[[BaseModel], str]
ResultParser = Callable[[str, str, int], tuple[str, dict[str, Any]]]


class EmptyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class CheckDefinition:
    key: str
    label: str
    description: str
    risk: CheckRisk
    parameter_model: type[BaseModel]
    command_builder: CommandBuilder
    result_parser: ResultParser


@dataclass(frozen=True)
class ResolvedProfile:
    template_key: str
    checks: tuple[CheckDefinition, ...]

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(check.key for check in self.checks)
