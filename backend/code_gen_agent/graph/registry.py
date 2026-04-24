"""Node registry for pluggable graph composition."""
from __future__ import annotations

from typing import Callable, TypeVar

from code_gen_agent.graph.base import BaseNode

T = TypeVar("T", bound=type[BaseNode])


class NodeRegistry:
    """Global registry of node classes keyed by name."""

    _registry: dict[str, type[BaseNode]] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[T], T]:
        def deco(node_cls: T) -> T:
            node_cls.name = name  # type: ignore[misc]
            cls._registry[name] = node_cls
            return node_cls

        return deco

    @classmethod
    def get(cls, name: str) -> type[BaseNode]:
        if name not in cls._registry:
            raise KeyError(f"Node not registered: {name}")
        return cls._registry[name]

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._registry.keys())

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()


def register_node(name: str) -> Callable[[T], T]:
    """Decorator: @register_node('intent') class IntentNode(BaseNode): ..."""
    return NodeRegistry.register(name)
