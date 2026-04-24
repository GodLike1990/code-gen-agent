"""Checker protocol and registry."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal, Protocol, TypeVar, runtime_checkable

Severity = Literal["info", "warn", "error"]


@dataclass
class Issue:
    file: str
    line: int
    severity: Severity
    message: str
    code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: Severity = "info"
    issues: list[Issue] = field(default_factory=list)
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "severity": self.severity,
            "issues": [i.to_dict() for i in self.issues],
            "raw_output": self.raw_output,
        }


@runtime_checkable
class Checker(Protocol):
    name: str

    async def run(
        self, workspace: str, files: dict[str, str], context: dict[str, Any] | None = None
    ) -> CheckResult: ...


T = TypeVar("T", bound=type[Checker])


class CheckerRegistry:
    _registry: dict[str, type[Checker]] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[T], T]:
        def deco(checker_cls: T) -> T:
            checker_cls.name = name  # type: ignore[misc]
            cls._registry[name] = checker_cls
            return checker_cls

        return deco

    @classmethod
    def get(cls, name: str) -> type[Checker]:
        if name not in cls._registry:
            raise KeyError(f"Checker not registered: {name}")
        return cls._registry[name]

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._registry.keys())


def register_checker(name: str):
    return CheckerRegistry.register(name)
