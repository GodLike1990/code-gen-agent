"""节点注册表，支持可插拔的图组装。"""
from __future__ import annotations

from typing import Callable, TypeVar

from code_gen_agent.graph.base import BaseNode

T = TypeVar("T", bound=type[BaseNode])


class NodeRegistry:
    """以名称为键的全局节点类注册表。"""

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
    """装饰器：@register_node('intent') class IntentNode(BaseNode): ..."""
    return NodeRegistry.register(name)
