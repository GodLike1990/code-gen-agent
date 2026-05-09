"""读取 JSON-Lines 日志文件并按 thread_id 过滤。

用于 /agent/runs/{tid}/logs 的回退方案：
当内存 LogCollector 中没有目标线程的记录时（如后端重启后）从磁盘读取。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_log_file(path: str, thread_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    """返回匹配 thread_id 的日志记录，按 ts 升序，上限 limit 条。

    文件缺失、权限不足或行格式错误时静默处理，返回 [] 或尽力而为的部分列表。
    调用方应将输出视为参考，而非权威来源。
    """
    if not path:
        return []
    p = Path(path)
    try:
        if not p.exists():
            return []
    except OSError:
        return []

    out: list[dict[str, Any]] = []
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("thread_id") == thread_id:
                    out.append(rec)
    except OSError:
        return out

    # 保留最近 limit 条，按时间升序
    if len(out) > limit:
        out = out[-limit:]
    return out
