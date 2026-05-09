"""抽象检查点后端接口。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CheckpointerBackend(Protocol):
    """LangGraph 可用作检查点的任意对象。

    LangGraph 检查点暴露 get_tuple、put、list（同步或异步）。
    此处不重复声明，该协议仅用于工厂返回值的类型检查。
    """

    def __repr__(self) -> str: ...
