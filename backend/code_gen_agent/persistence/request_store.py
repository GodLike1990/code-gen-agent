"""每请求本地文件存储。

在磁盘上保存用户可见的请求记录，刻意与 LangGraph 检查点解耦
（检查点负责图状态）。每个 thread_id 在 requests_dir 下对应一个 JSON 文件。

Schema::

    {
        "thread_id": str,
        "created_at": ISO-8601 UTC,
        "updated_at": ISO-8601 UTC,
        "request":    str,                        # 原始用户输入
        "status":     "running" | "done" | "aborted" | "failed" | "interrupted" | "cancelled",
        "summary":    str | None                  # 可选的终态摘要
    }
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("code_gen_agent.request_store")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RequestStore:
    """以每线程 JSON 文件为原子单元的用户请求记录存储。"""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ 路径
    def _path(self, thread_id: str) -> Path:
        # 保守消毒：thread id 为服务端生成的 UUID，但仍防范路径穿越
        safe = thread_id.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe}.json"

    # ------------------------------------------------------------------ API
    def save(self, thread_id: str, request: str) -> dict[str, Any]:
        now = _now()
        rec = {
            "thread_id": thread_id,
            "created_at": now,
            "updated_at": now,
            "request": request,
            "status": "running",
            "summary": None,
        }
        self._atomic_write(self._path(thread_id), rec)
        return rec

    def update(
        self,
        thread_id: str,
        *,
        status: str | None = None,
        summary: str | None = None,
    ) -> dict[str, Any] | None:
        p = self._path(thread_id)
        if not p.exists():
            return None
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("request_store: failed to read %s: %s", p, exc)
            return None
        if status is not None:
            rec["status"] = status
        if summary is not None:
            rec["summary"] = summary
        rec["updated_at"] = _now()
        self._atomic_write(p, rec)
        return rec

    def get(self, thread_id: str) -> dict[str, Any] | None:
        p = self._path(thread_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("request_store: failed to read %s: %s", p, exc)
            return None

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for f in self.root.glob("*.json"):
            try:
                items.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("request_store: skipping corrupt file %s: %s", f, exc)
                continue
        items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return items

    # ------------------------------------------------------------------ IO
    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)


__all__ = ["RequestStore"]
