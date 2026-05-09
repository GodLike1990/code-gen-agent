"""按 thread_id 聚合 token 用量。"""
from __future__ import annotations

import threading
from typing import Any

from code_gen_agent.llm.usage import UsageTracker


class UsageAggregator:
    """每个 thread_id 持有一个 UsageTracker。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._trackers: dict[str, UsageTracker] = {}

    def get_or_create(self, thread_id: str) -> UsageTracker:
        with self._lock:
            if thread_id not in self._trackers:
                self._trackers[thread_id] = UsageTracker()
            return self._trackers[thread_id]

    def snapshot(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            tracker = self._trackers.get(thread_id)
        return tracker.snapshot() if tracker else None

    def drop(self, thread_id: str) -> None:
        with self._lock:
            self._trackers.pop(thread_id, None)
