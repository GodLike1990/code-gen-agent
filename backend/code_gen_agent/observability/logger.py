"""结构化 JSON 日志，支持按线程收集。"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# 标准 LogRecord 属性，不作为自定义 extra 字段转发
_STDLIB_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
})


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """返回 record 上通过 extra= 设置的所有非标准属性。"""
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
        # 合并所有 extra 字段，允许调用方传入任意结构化数据
        payload.update(_extra_fields(record))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class LogCollector(logging.Handler):
    """每个 thread_id 保留最近 N 条日志，可通过 API 查询。"""

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
        # 合并所有 extra 字段，保持内存收集器的完整性
        entry.update(_extra_fields(record))
        with self._lock:
            self._store[tid].append(entry)

    def get(self, thread_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._store.get(thread_id, ()))


_collector: LogCollector | None = None


def configure_logging(level: str = "INFO", log_file: str | None = None) -> LogCollector:
    """配置根 logger，使用 JSON 格式化器和内存收集器。

    提供 log_file 时日志仅写入滚动文件（不输出到控制台）。
    未提供时回退到 stdout，确保服务在不支持文件日志的环境中仍可调试。
    """
    global _collector
    root = logging.getLogger("code_gen_agent")
    root.setLevel(level.upper())
    # 避免重复配置时叠加 handler
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
            # 日志目录不可写时回退到 stdout
            root.warning("failed to enable file logging at %s: %s", log_file, exc)

    if not file_handler_added:
        # 无文件 handler 时仅使用 stdout 作为回退
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
