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

# Standard LogRecord attributes that must not be forwarded as custom extras.
_STDLIB_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
})


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """Return all non-stdlib attributes set via ``extra=`` on the record."""
    return {
        k: v
        for k, v in record.__dict__.items()
        if k not in _STDLIB_ATTRS and not k.startswith("_")
    }


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge all extra fields so callers can pass arbitrary structured data.
        payload.update(_extra_fields(record))
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
        entry: dict[str, Any] = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge all extra fields for full fidelity in the in-memory collector.
        entry.update(_extra_fields(record))
        with self._lock:
            self._store[tid].append(entry)

    def get(self, thread_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._store.get(thread_id, ()))


_collector: LogCollector | None = None


def configure_logging(level: str = "INFO", log_file: str | None = None) -> LogCollector:
    """Set up root logger with JSON formatter and in-memory collector.

    When ``log_file`` is provided logs go to the rotating file only (no
    console noise). Without a log file, stdout is used as a fallback so
    the service remains debuggable in environments where file logging is
    unavailable.
    """
    global _collector
    root = logging.getLogger("code_gen_agent")
    root.setLevel(level.upper())
    # avoid duplicate handlers on re-configure
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = _JsonFormatter()
    file_handler_added = False

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
            file_handler_added = True
        except OSError as exc:
            # Fall back to stdout when the log directory is not writable.
            root.warning("failed to enable file logging at %s: %s", log_file, exc)

    if not file_handler_added:
        # No file handler available — use stdout as fallback only.
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

    _collector = LogCollector()
    root.addHandler(_collector)
    root.propagate = False
    return _collector


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"code_gen_agent.{name}")


def get_collector() -> LogCollector | None:
    return _collector
