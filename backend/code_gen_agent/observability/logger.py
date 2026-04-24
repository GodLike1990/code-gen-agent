"""Structured JSON logging with per-thread collection."""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("thread_id", "node", "duration_ms", "event"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class LogCollector(logging.Handler):
    """Keeps the last N log records per thread_id, queryable via API."""

    def __init__(self, max_per_thread: int = 1000) -> None:
        super().__init__()
        self._store: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=max_per_thread)
        )
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        tid = getattr(record, "thread_id", None)
        if not tid:
            return
        entry = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "node": getattr(record, "node", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "event": getattr(record, "event", None),
        }
        with self._lock:
            self._store[tid].append(entry)

    def get(self, thread_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._store.get(thread_id, ()))


_collector: LogCollector | None = None


def configure_logging(level: str = "INFO", log_file: str | None = None) -> LogCollector:
    """Set up root logger with JSON formatter and in-memory collector."""
    global _collector
    root = logging.getLogger("code_gen_agent")
    root.setLevel(level.upper())
    # avoid duplicate handlers on re-configure
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = _JsonFormatter()
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    if log_file:
        try:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError as exc:
            # Don't let a log-dir permission issue take the server down;
            # stdout logging still works.
            root.warning("failed to enable file logging at %s: %s", log_file, exc)

    _collector = LogCollector()
    root.addHandler(_collector)
    root.propagate = False
    return _collector


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"code_gen_agent.{name}")


def get_collector() -> LogCollector | None:
    return _collector
