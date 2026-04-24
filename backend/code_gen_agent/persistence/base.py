"""Abstract checkpointer backend interface."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CheckpointerBackend(Protocol):
    """Any object that LangGraph can use as a checkpointer.

    LangGraph checkpointers expose `get_tuple`, `put`, `list` (sync or async).
    We don't re-declare them here; this protocol is only used for type-checking
    the factory return.
    """

    def __repr__(self) -> str: ...
