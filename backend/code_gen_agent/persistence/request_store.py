"""Per-request local file store.

Keeps the *user-facing request record* on disk, deliberately decoupled from
the LangGraph checkpointer (which owns graph state). One JSON file per
thread_id under ``requests_dir``.

Schema::

    {
        "thread_id": str,
        "created_at": ISO-8601 UTC,
        "updated_at": ISO-8601 UTC,
        "request":    str,                        # original user text
        "status":     "running" | "done" | "aborted" | "failed" | "interrupted" | "cancelled",
        "summary":    str | None                  # optional end-state summary
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
    """Atomic JSON-per-thread storage for user request records."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths
    def _path(self, thread_id: str) -> Path:
        # Very conservative sanitisation: thread ids are server-generated UUIDs,
        # but guard against path traversal just in case.
        safe = thread_id.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe}.json"

    # ------------------------------------------------------------------ api
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

    # ------------------------------------------------------------------ io
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
